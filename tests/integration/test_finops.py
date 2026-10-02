import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from ai_arbiter.core.config import ReportingCurrencySettings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.tenancy import TenantContext
from ai_arbiter.core.errors import ConflictError, NotFoundError
from ai_arbiter.core.interaction import Interaction, InteractionStatus
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.ports.llm import Usage
from ai_arbiter.gateway.finops.budgets import BudgetLevel, BudgetPeriod, BudgetService
from ai_arbiter.gateway.finops.catalogue import load_catalogue
from ai_arbiter.gateway.finops.metering import UsageMeter, estimate_usage, usage_by_scope
from ai_arbiter.gateway.finops.model import UsageRollup
from ai_arbiter.gateway.identity.model import ScopeType
from tests.support import deployment, mock_router

NOW = datetime(2026, 10, 15, 9, 30, tzinfo=UTC)
TEAM, PROJECT, PRINCIPAL = new_id(), new_id(), new_id()


class FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


def interaction(
    tenant_id: UUID,
    *,
    cost: str | None = "1.5",
    status: InteractionStatus = InteractionStatus.OK,
    estimated: bool = False,
    at: datetime = NOW,
    project_id: UUID | None = PROJECT,
    tokens: tuple[int | None, int | None] = (100, 50),
) -> Interaction:
    identifier = new_id()
    return Interaction(
        id=identifier,
        tenant_id=tenant_id,
        team_id=TEAM,
        project_id=project_id,
        principal_id=PRINCIPAL,
        source_record_id=str(identifier),
        started_at=at,
        status=status.value,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
        usage_estimated=estimated,
        cost_estimate=Decimal(cost) if cost is not None else None,
        currency="USD",
    )


@pytest.fixture
def meter() -> UsageMeter:
    return UsageMeter(load_catalogue())


async def record(database: Database, meter: UsageMeter, *interactions: Interaction) -> None:
    for item in interactions:
        async with database.transaction() as session:
            await meter.record(session, item)


async def totals(database: Database, tenant_id: UUID, scope: ScopeType = ScopeType.TENANT):  # type: ignore[no-untyped-def]
    async with database.session() as session:
        return await usage_by_scope(
            session, tenant_id, scope, start=date(2026, 10, 1), end=date(2026, 10, 31)
        )


def test_the_meter_prices_a_deployment_from_the_catalogue(meter: UsageMeter) -> None:
    _, targets, _ = mock_router(
        [
            deployment("small", model="mock-small"),
            deployment("alias", model="whatever", priced_as="mock-large"),
            deployment("unpriced", model="unknown-model"),
        ]
    )
    usage = Usage(input_tokens=1000, output_tokens=1000)

    assert meter.cost(targets[0], usage) == Decimal("0.00075")
    assert meter.cost(targets[1], usage) == Decimal("0.0125")
    assert meter.cost(targets[2], usage) is None
    assert meter.cost(targets[0], None) is None
    assert meter.comparable_cost(targets[0]) == Decimal("0.75")
    assert meter.comparable_cost(targets[2]) is None


def test_an_estimate_rounds_up_and_is_flagged() -> None:
    usage = estimate_usage(prompt_characters=9, completion_characters=8, chars_per_token=4)

    assert (usage.input_tokens, usage.output_tokens, usage.estimated) == (3, 2, True)
    assert estimate_usage(0, 0, 4).input_tokens == 0


async def test_an_interaction_is_added_to_every_scope_it_belongs_to(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    await record(database, meter, interaction(tenant_id))

    async with database.session() as session:
        rows = (await session.scalars(select(UsageRollup))).all()

    assert {(row.scope_type, row.scope_id) for row in rows} == {
        ("tenant", tenant_id),
        ("team", TEAM),
        ("project", PROJECT),
        ("principal", PRINCIPAL),
    }
    assert all(row.day == date(2026, 10, 15) and row.currency == "USD" for row in rows)
    assert all(row.cost_estimate == Decimal("1.5") for row in rows)


async def test_amounts_are_summed_exactly(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    await record(
        database,
        meter,
        *[interaction(tenant_id, cost="0.000000001") for _ in range(3)],
        interaction(tenant_id, cost="0.1"),
        interaction(tenant_id, cost="0.2"),
    )

    lines = await totals(database, tenant_id)

    assert len(lines) == 1
    assert lines[0].totals.cost_estimate == Decimal("0.300000003")
    assert (lines[0].totals.requests, lines[0].totals.input_tokens) == (5, 500)


async def test_denied_failed_unpriced_and_estimated_are_counted_apart(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    await record(
        database,
        meter,
        interaction(tenant_id, cost="1"),
        interaction(tenant_id, cost="2", estimated=True),
        interaction(tenant_id, cost=None, tokens=(None, None)),
        interaction(tenant_id, cost=None, status=InteractionStatus.DENIED, tokens=(None, None)),
        interaction(tenant_id, cost=None, status=InteractionStatus.ERROR, tokens=(None, None)),
        interaction(tenant_id, cost="4", status=InteractionStatus.ABORTED),
    )

    result = (await totals(database, tenant_id))[0].totals

    assert (result.requests, result.denied, result.failed) == (6, 1, 1)
    assert (result.unpriced, result.estimated) == (1, 1)
    assert result.cost_estimate == Decimal(7)
    assert result.estimated_cost == Decimal(2)
    assert result.input_tokens == 300


async def test_usage_is_grouped_by_scope_and_limited_to_the_period(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    other_project = new_id()
    await record(
        database,
        meter,
        interaction(tenant_id, cost="1"),
        interaction(tenant_id, cost="2", project_id=other_project),
        interaction(tenant_id, cost="4", project_id=None),
        interaction(tenant_id, cost="8", at=NOW - timedelta(days=30)),
    )

    by_project = {
        line.scope_id: line.totals.cost_estimate
        for line in await totals(database, tenant_id, ScopeType.PROJECT)
    }
    tenant_total = (await totals(database, tenant_id))[0].totals.cost_estimate

    assert by_project == {PROJECT: Decimal(1), other_project: Decimal(2)}
    assert tenant_total == Decimal(7)


async def test_concurrent_requests_do_not_lose_counts(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    await asyncio.gather(
        *(record(database, meter, interaction(tenant_id, cost="0.5")) for _ in range(20))
    )

    result = (await totals(database, tenant_id))[0].totals

    assert result.requests == 20
    assert result.cost_estimate == Decimal(10)


async def test_usage_of_one_tenant_is_invisible_to_another(
    database: Database, tenant_id: UUID, other_tenant_id: UUID, meter: UsageMeter
) -> None:
    await record(database, meter, interaction(tenant_id))

    assert await totals(database, other_tenant_id) == []
    assert await totals(database, other_tenant_id, ScopeType.PROJECT) == []


async def create_budget(
    database: Database, service: BudgetService, tenant_id: UUID, **values: object
) -> UUID:
    defaults: dict[str, object] = {
        "scope_type": ScopeType.PROJECT,
        "scope_id": PROJECT,
        "period": BudgetPeriod.MONTH,
        "limit_amount": Decimal(10),
        "hard": True,
    }
    async with database.transaction() as session:
        return (await service.create(session, tenant_id, **{**defaults, **values})).id  # type: ignore[arg-type]


def context(tenant_id: UUID, project_id: UUID | None = PROJECT) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id, team_id=TEAM, project_id=project_id, principal_id=PRINCIPAL
    )


async def status(database: Database, service: BudgetService, ctx: TenantContext):  # type: ignore[no-untyped-def]
    async with database.session() as session:
        return await service.status(session, ctx)


async def test_a_budget_goes_from_ok_to_soft_to_exceeded(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    service = BudgetService("USD", clock=FixedClock())
    await create_budget(database, service, tenant_id)
    levels = []

    for cost in ("7.9", "0.1", "2"):
        await record(database, meter, interaction(tenant_id, cost=cost))
        state = await status(database, service, context(tenant_id))
        levels.append((state.budgets[0].level, state.soft_exceeded, state.hard_exceeded))

    assert levels == [
        (BudgetLevel.OK, False, False),
        (BudgetLevel.SOFT, True, False),
        (BudgetLevel.EXCEEDED, True, True),
    ]
    assert state.budgets[0].spent == Decimal(10)


async def test_a_soft_budget_never_counts_as_hard_exceeded(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    service = BudgetService("USD", clock=FixedClock())
    await create_budget(database, service, tenant_id, hard=False)
    await record(database, meter, interaction(tenant_id, cost="50"))

    state = await status(database, service, context(tenant_id))

    assert state.budgets[0].level is BudgetLevel.EXCEEDED
    assert state.soft_exceeded
    assert not state.hard_exceeded


async def test_a_budget_covers_only_its_scope(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    service = BudgetService("USD", clock=FixedClock())
    await create_budget(database, service, tenant_id)
    await record(database, meter, interaction(tenant_id, cost="50"))

    elsewhere = await status(database, service, context(tenant_id, project_id=new_id()))

    assert elsewhere.budgets == ()
    assert not elsewhere.hard_exceeded


async def test_a_monthly_budget_starts_again_each_month_and_a_daily_one_each_day(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    clock = FixedClock()
    service = BudgetService("USD", clock=clock)
    await create_budget(database, service, tenant_id)
    await create_budget(
        database,
        service,
        tenant_id,
        scope_type=ScopeType.TENANT,
        scope_id=None,
        period=BudgetPeriod.DAY,
        limit_amount=Decimal(5),
    )
    await record(database, meter, interaction(tenant_id, cost="6"))

    same_day = await status(database, service, context(tenant_id))
    clock.current = NOW + timedelta(days=1)
    next_day = await status(database, service, context(tenant_id))
    clock.current = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    next_month = await status(database, service, context(tenant_id))

    def spent(state: object) -> dict[str, Decimal]:
        return {b.period: b.spent for b in state.budgets}  # type: ignore[attr-defined]

    assert spent(same_day) == {"month": Decimal(6), "day": Decimal(6)}
    assert spent(next_day) == {"month": Decimal(6), "day": Decimal(0)}
    assert spent(next_month) == {"month": Decimal(0), "day": Decimal(0)}
    assert same_day.hard_exceeded
    assert not next_day.hard_exceeded


async def test_a_budget_in_the_reporting_currency_is_checked_at_the_configured_rate(
    database: Database, tenant_id: UUID, meter: UsageMeter
) -> None:
    reporting = ReportingCurrencySettings(currency="EUR", rate="0.5", rate_as_of=date(2026, 10, 1))
    service = BudgetService("USD", reporting, FixedClock())
    await create_budget(database, service, tenant_id, currency="EUR", limit_amount=Decimal(10))
    await record(database, meter, interaction(tenant_id, cost="12"))

    state = await status(database, service, context(tenant_id))

    assert (state.budgets[0].spent, state.budgets[0].currency) == (Decimal(6), "EUR")
    assert state.budgets[0].level is BudgetLevel.OK


async def test_budgets_that_cannot_be_checked_or_make_no_sense_are_refused(
    database: Database, tenant_id: UUID
) -> None:
    service = BudgetService("USD")
    await create_budget(database, service, tenant_id)

    cases: list[tuple[dict[str, object], str]] = [
        ({"currency": "GBP", "period": BudgetPeriod.DAY}, "no conversion rate"),
        ({"limit_amount": Decimal(0), "period": BudgetPeriod.DAY}, "greater than zero"),
        ({"soft_threshold_percent": 0, "period": BudgetPeriod.DAY}, "between 1 and 100"),
        ({"scope_id": None, "period": BudgetPeriod.DAY}, "needs its id"),
        ({}, "already has a budget"),
    ]
    for values, message in cases:
        with pytest.raises(ConflictError, match=message):
            await create_budget(database, service, tenant_id, **values)


async def test_budgets_are_listed_and_deleted_within_their_tenant(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    service = BudgetService("USD")
    budget_id = await create_budget(database, service, tenant_id)

    async with database.transaction() as session:
        assert [b.id for b in await service.list(session, tenant_id)] == [budget_id]
        assert await service.list(session, other_tenant_id) == []
        with pytest.raises(NotFoundError):
            await service.delete(session, other_tenant_id, budget_id)
        await service.delete(session, tenant_id, budget_id)
        assert await service.list(session, tenant_id) == []
