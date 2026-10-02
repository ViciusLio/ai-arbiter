"""Budgets: a spending limit on a scope for a day or a month, soft or hard."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.config.settings import ReportingCurrencySettings, parse_decimal
from ai_arbiter.core.domain.tenancy import TenantContext
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.errors import ConflictError, NotFoundError
from ai_arbiter.gateway.finops.model import Budget, UsageRollup
from ai_arbiter.gateway.identity.model import ScopeType


class BudgetPeriod(StrEnum):
    DAY = "day"
    MONTH = "month"


class BudgetLevel(StrEnum):
    OK = "ok"
    SOFT = "soft"  # past the soft threshold
    EXCEEDED = "exceeded"  # at or past the limit


@dataclass(frozen=True)
class BudgetState:
    budget_id: UUID
    scope_type: str
    scope_id: UUID
    period: str
    hard: bool
    limit_amount: Decimal
    spent: Decimal
    currency: str
    level: BudgetLevel


@dataclass(frozen=True)
class BudgetStatus:
    budgets: tuple[BudgetState, ...] = ()

    @property
    def hard_exceeded(self) -> bool:
        return any(b.hard and b.level is BudgetLevel.EXCEEDED for b in self.budgets)

    @property
    def soft_exceeded(self) -> bool:
        return any(b.level is not BudgetLevel.OK for b in self.budgets)


def period_start(period: str, today: date) -> date:
    return today.replace(day=1) if period == BudgetPeriod.MONTH.value else today


class BudgetService:
    """Budgets are compared with the roll-ups, which are in the catalogue's currency.

    A budget may be written in that currency or in the reporting currency; in the second
    case spending is converted with the configured rate before the comparison. A burst
    of concurrent requests can overshoot a limit slightly: each of them reads the
    roll-ups before any of them is recorded.
    """

    def __init__(
        self,
        catalogue_currency: str,
        reporting: ReportingCurrencySettings | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._currency = catalogue_currency
        self._reporting = reporting
        self._clock = clock if clock is not None else SystemClock()

    def _rate(self, currency: str) -> Decimal | None:
        """Factor from the catalogue's currency to ``currency``; ``None`` if unknown."""
        if currency == self._currency:
            return Decimal(1)
        if self._reporting is not None and currency == self._reporting.currency:
            return parse_decimal(self._reporting.rate, positive=True)
        return None

    async def create(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        scope_type: ScopeType,
        scope_id: UUID | None,
        period: BudgetPeriod,
        limit_amount: Decimal,
        currency: str | None = None,
        soft_threshold_percent: int = 80,
        hard: bool = False,
    ) -> Budget:
        currency = currency or self._currency
        if self._rate(currency) is None:
            raise ConflictError(
                f"a budget in {currency} cannot be checked: prices are in {self._currency} "
                "and no conversion rate to that currency is configured"
            )
        if limit_amount <= 0:
            raise ConflictError("a budget limit must be greater than zero")
        if not 1 <= soft_threshold_percent <= 100:
            raise ConflictError("the soft threshold must be between 1 and 100 percent")
        target = tenant_id if scope_type is ScopeType.TENANT else scope_id
        if target is None:
            raise ConflictError(f"a budget on a {scope_type.value} needs its id")
        existing = await session.scalar(
            select(Budget).where(
                Budget.tenant_id == tenant_id,
                Budget.scope_type == scope_type.value,
                Budget.scope_id == target,
                Budget.period == period.value,
            )
        )
        if existing is not None:
            raise ConflictError("this scope already has a budget for that period")
        budget = Budget(
            tenant_id=tenant_id,
            scope_type=scope_type.value,
            scope_id=target,
            period=period.value,
            limit_amount=limit_amount,
            currency=currency,
            soft_threshold_percent=soft_threshold_percent,
            hard=hard,
        )
        session.add(budget)
        await session.flush()
        return budget

    async def list(self, session: AsyncSession, tenant_id: UUID) -> Sequence[Budget]:
        return (
            await session.scalars(
                select(Budget)
                .where(Budget.tenant_id == tenant_id)
                .order_by(Budget.created_at, Budget.id)
            )
        ).all()

    async def delete(self, session: AsyncSession, tenant_id: UUID, budget_id: UUID) -> None:
        budget = await session.scalar(
            select(Budget).where(Budget.tenant_id == tenant_id, Budget.id == budget_id)
        )
        if budget is None:
            raise NotFoundError(f"budget {budget_id} not found")
        await session.delete(budget)
        await session.flush()

    async def _spent(self, session: AsyncSession, budget: Budget, today: date) -> Decimal:
        total = await session.scalar(
            select(func.sum(UsageRollup.cost_estimate)).where(
                UsageRollup.tenant_id == budget.tenant_id,
                UsageRollup.scope_type == budget.scope_type,
                UsageRollup.scope_id == budget.scope_id,
                UsageRollup.currency == self._currency,
                UsageRollup.day >= period_start(budget.period, today),
                UsageRollup.day <= today,
            )
        )
        rate = self._rate(budget.currency) or Decimal(1)
        return Decimal(total or 0) * rate

    async def state(self, session: AsyncSession, budget: Budget) -> BudgetState:
        spent = await self._spent(session, budget, self._clock.now().date())
        if spent >= budget.limit_amount:
            level = BudgetLevel.EXCEEDED
        elif spent * 100 >= budget.limit_amount * budget.soft_threshold_percent:
            level = BudgetLevel.SOFT
        else:
            level = BudgetLevel.OK
        return BudgetState(
            budget_id=budget.id,
            scope_type=budget.scope_type,
            scope_id=budget.scope_id,
            period=budget.period,
            hard=budget.hard,
            limit_amount=budget.limit_amount,
            spent=spent,
            currency=budget.currency,
            level=level,
        )

    async def status(self, session: AsyncSession, context: TenantContext) -> BudgetStatus:
        """The state of every budget that covers a request made in this context."""
        scopes = [
            (ScopeType.TENANT, context.tenant_id),
            (ScopeType.TEAM, context.team_id),
            (ScopeType.PROJECT, context.project_id),
            (ScopeType.PRINCIPAL, context.principal_id),
            (ScopeType.AI_SYSTEM, context.ai_system_id),
        ]
        budgets = (
            await session.scalars(
                select(Budget)
                .where(
                    Budget.tenant_id == context.tenant_id,
                    or_(
                        *(
                            (Budget.scope_type == scope_type.value) & (Budget.scope_id == scope_id)
                            for scope_type, scope_id in scopes
                            if scope_id is not None
                        )
                    ),
                )
                .order_by(Budget.created_at, Budget.id)
            )
        ).all()
        return BudgetStatus(tuple([await self.state(session, budget) for budget in budgets]))
