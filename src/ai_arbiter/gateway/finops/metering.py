"""Metering: price an interaction, record it, keep the roll-ups current."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.interaction import Interaction, InteractionStatus
from ai_arbiter.core.ports.llm import Usage
from ai_arbiter.gateway.finops.catalogue import ModelPrice, PriceCatalogue
from ai_arbiter.gateway.finops.model import UsageRollup
from ai_arbiter.gateway.identity.model import ScopeType
from ai_arbiter.gateway.llm_router.deployments import Target

_COMPLETED = (InteractionStatus.OK.value, InteractionStatus.ABORTED.value)


def estimate_usage(
    prompt_characters: int, completion_characters: int, chars_per_token: int
) -> Usage:
    """Token counts guessed from text length, flagged as estimated (ADR-0031)."""
    return Usage(
        input_tokens=-(-prompt_characters // chars_per_token),
        output_tokens=-(-completion_characters // chars_per_token),
        estimated=True,
    )


@dataclass(frozen=True)
class UsageTotals:
    requests: int = 0
    denied: int = 0
    failed: int = 0
    unpriced: int = 0
    estimated: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_estimate: Decimal = Decimal(0)
    estimated_cost: Decimal = Decimal(0)


@dataclass(frozen=True)
class UsageLine:
    scope_type: str
    scope_id: UUID
    currency: str
    totals: UsageTotals = field(default_factory=UsageTotals)


class UsageMeter:
    def __init__(self, catalogue: PriceCatalogue) -> None:
        self.catalogue = catalogue

    def comparable_cost(self, target: Target) -> Decimal | None:
        """What the cost routing strategy sorts by: input plus output price."""
        price = self._price(target)
        return None if price is None else price.input + price.output

    def _price(self, target: Target) -> ModelPrice | None:
        return self.catalogue.price(
            target.deployment.provider, target.config.price_model, target.deployment.region
        )

    def cost(self, target: Target, usage: Usage | None) -> Decimal | None:
        """Estimated cost, or ``None`` without a price or without token counts."""
        price = self._price(target)
        if price is None or usage is None:
            return None
        return price.cost(usage)

    async def record(self, session: AsyncSession, interaction: Interaction) -> None:
        """Store the interaction and add it to the roll-up of every scope it belongs to."""
        session.add(interaction)
        await session.flush()
        completed = interaction.status in _COMPLETED
        cost = interaction.cost_estimate if completed else None
        increments: dict[str, int | Decimal] = {
            "requests": 1,
            "denied": int(interaction.status == InteractionStatus.DENIED.value),
            "failed": int(interaction.status == InteractionStatus.ERROR.value),
            "unpriced": int(completed and cost is None),
            "estimated": int(completed and interaction.usage_estimated),
            "input_tokens": (interaction.input_tokens or 0) if completed else 0,
            "output_tokens": (interaction.output_tokens or 0) if completed else 0,
            "cost_estimate": cost or Decimal(0),
            "estimated_cost": (cost or Decimal(0)) if interaction.usage_estimated else Decimal(0),
        }
        scopes: list[tuple[ScopeType, UUID | None]] = [
            (ScopeType.TENANT, interaction.tenant_id),
            (ScopeType.TEAM, interaction.team_id),
            (ScopeType.PROJECT, interaction.project_id),
            (ScopeType.PRINCIPAL, interaction.principal_id),
            (ScopeType.AI_SYSTEM, interaction.ai_system_id),
        ]
        currency = interaction.currency or self.catalogue.currency
        for scope_type, scope_id in scopes:
            if scope_id is not None:
                await self._add(
                    session,
                    interaction.tenant_id,
                    scope_type.value,
                    scope_id,
                    interaction.started_at.date(),
                    currency,
                    increments,
                )

    @staticmethod
    async def _add(
        session: AsyncSession,
        tenant_id: UUID,
        scope_type: str,
        scope_id: UUID,
        day: date,
        currency: str,
        increments: dict[str, int | Decimal],
    ) -> None:
        """Add to a roll-up row, creating it if needed.

        The update is a single statement of the form ``x = x + n``, so concurrent
        requests cannot overwrite each other's counts.
        """
        key = {
            "tenant_id": tenant_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "day": day,
            "currency": currency,
        }
        statement = (
            update(UsageRollup)
            .where(*(getattr(UsageRollup, name) == value for name, value in key.items()))
            .values(
                {name: getattr(UsageRollup, name) + value for name, value in increments.items()}
            )
            .execution_options(synchronize_session=False)
        )
        if (await session.execute(statement)).rowcount:  # type: ignore[attr-defined]
            return
        try:
            async with session.begin_nested():
                session.add(UsageRollup(**key, **increments))
        except IntegrityError:
            # Another request created the row in the meantime.
            await session.execute(statement)


async def usage_by_scope(
    session: AsyncSession,
    tenant_id: UUID,
    scope_type: ScopeType,
    *,
    start: date,
    end: date,
) -> Sequence[UsageLine]:
    """Totals per scope and currency for the days from ``start`` to ``end`` inclusive."""
    counters = ("requests", "denied", "failed", "unpriced", "estimated")
    tokens = ("input_tokens", "output_tokens")
    amounts = ("cost_estimate", "estimated_cost")
    rows = await session.execute(
        select(
            UsageRollup.scope_id,
            UsageRollup.currency,
            *(
                func.sum(getattr(UsageRollup, name)).label(name)
                for name in (*counters, *tokens, *amounts)
            ),
        )
        .where(
            UsageRollup.tenant_id == tenant_id,
            UsageRollup.scope_type == scope_type.value,
            UsageRollup.day >= start,
            UsageRollup.day <= end,
        )
        .group_by(UsageRollup.scope_id, UsageRollup.currency)
        .order_by(UsageRollup.scope_id, UsageRollup.currency)
    )
    return [
        UsageLine(
            scope_type=scope_type.value,
            scope_id=row.scope_id,
            currency=row.currency,
            totals=UsageTotals(
                requests=int(row.requests),
                denied=int(row.denied),
                failed=int(row.failed),
                unpriced=int(row.unpriced),
                estimated=int(row.estimated),
                input_tokens=int(row.input_tokens),
                output_tokens=int(row.output_tokens),
                cost_estimate=Decimal(row.cost_estimate),
                estimated_cost=Decimal(row.estimated_cost),
            ),
        )
        for row in rows
    ]
