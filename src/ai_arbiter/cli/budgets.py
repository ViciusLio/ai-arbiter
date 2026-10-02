"""``arbiter budgets``: spending limits, from the local database."""

from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy import select

from ai_arbiter.cli.common import fail, open_database, run, settings_from, tenant_id_for
from ai_arbiter.compliance.inventory.model import AISystem
from ai_arbiter.core.audit import AuditRecord, DatabaseAuditLog
from ai_arbiter.core.config.settings import Settings, parse_decimal
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.errors import ArbiterError, NotFoundError
from ai_arbiter.gateway.finops.budgets import BudgetPeriod, BudgetService, BudgetState
from ai_arbiter.gateway.finops.catalogue import load_catalogue
from ai_arbiter.gateway.identity.model import ScopeType

app = typer.Typer(help="Soft and hard spending limits.", no_args_is_help=True)

TenantSlug = Annotated[str, typer.Option("--tenant", help="Tenant slug.")]


def _service(settings: Settings) -> BudgetService:
    return BudgetService(load_catalogue(settings.finops).currency, settings.finops.reporting)


def _line(state: BudgetState) -> str:
    kind = "hard" if state.hard else "soft"
    return (
        f"{str(state.budget_id)[:8]}  {state.scope_type:<10} {state.scope_id}  "
        f"{state.period:<6} {kind:<5} {state.spent:.6f} of {state.limit_amount:.6f} "
        f"{state.currency}  {state.level.value}"
    )


async def _list(settings: Settings, tenant: str) -> list[BudgetState]:
    service = _service(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            return [
                await service.state(session, budget)
                for budget in await service.list(session, tenant_id)
            ]


@app.command("list")
def list_budgets(ctx: typer.Context, tenant: TenantSlug = LOCAL_TENANT_SLUG) -> None:
    """List budgets with what has been spent in the current period."""
    states = run(_list(settings_from(ctx), tenant))
    if not states:
        typer.echo("No budget is set. Create one with: arbiter budgets create")
        return
    for state in states:
        typer.echo(_line(state))
    typer.echo("")
    typer.echo("Spending is an estimate from the price catalogue, not an invoice.")


async def _create(
    settings: Settings,
    tenant: str,
    scope: ScopeType,
    scope_id: UUID | None,
    system: str | None,
    period: BudgetPeriod,
    limit: str,
    currency: str | None,
    soft_threshold: int,
    hard: bool,
) -> BudgetState:
    try:
        amount = parse_decimal(limit, positive=True)
    except ValueError as error:
        raise ArbiterError(f"--limit: {error}") from error
    service = _service(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            if system is not None:
                scope_id = await session.scalar(
                    select(AISystem.id).where(
                        AISystem.tenant_id == tenant_id, AISystem.key == system
                    )
                )
                if scope_id is None:
                    raise NotFoundError(f"no system with key '{system}'")
            budget = await service.create(
                session,
                tenant_id,
                scope_type=scope,
                scope_id=scope_id,
                period=period,
                limit_amount=amount,
                currency=currency,
                soft_threshold_percent=soft_threshold,
                hard=hard,
            )
            await DatabaseAuditLog().append(
                session,
                tenant_id,
                AuditRecord(
                    action="budget.created",
                    outcome="ok",
                    resource_type="budget",
                    resource_id=str(budget.id),
                ),
            )
            return await service.state(session, budget)


@app.command("create")
def create(
    ctx: typer.Context,
    limit: Annotated[str, typer.Option("--limit", help='Amount per period, for example "50".')],
    scope: Annotated[ScopeType, typer.Option(help="What the budget is on.")] = ScopeType.TENANT,
    scope_id: Annotated[
        UUID | None, typer.Option("--id", help="Identifier of the team, project or principal.")
    ] = None,
    system: Annotated[
        str | None, typer.Option("--system", help="Key of a declared AI system.")
    ] = None,
    period: Annotated[BudgetPeriod, typer.Option(help="day or month.")] = BudgetPeriod.MONTH,
    currency: Annotated[
        str | None, typer.Option(help="Default: the currency of the price catalogue.")
    ] = None,
    soft_threshold: Annotated[
        int, typer.Option(min=1, max=100, help="Percent of the limit from which it warns.")
    ] = 80,
    hard: Annotated[
        bool, typer.Option("--hard", help="Deny requests once the limit is reached.")
    ] = False,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Set a budget on the tenant, a team, a project, a principal or an AI system.

    A soft budget warns; a hard one makes the gateway deny requests once it is reached.
    """
    if system is not None:
        if scope_id is not None:
            raise fail(ArbiterError("use either --id or --system KEY"))
        scope = ScopeType.AI_SYSTEM
    state = run(
        _create(
            settings_from(ctx),
            tenant,
            scope,
            scope_id,
            system,
            period,
            limit,
            currency,
            soft_threshold,
            hard,
        )
    )
    typer.echo(_line(state))


async def _delete(settings: Settings, tenant: str, reference: str) -> UUID:
    service = _service(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            matches = [
                budget.id
                for budget in await service.list(session, tenant_id)
                if str(budget.id).startswith(reference.lower())
            ]
            if len(matches) != 1:
                problem = "no budget" if not matches else "more than one budget"
                raise NotFoundError(f"{problem} with an id that starts with '{reference}'")
            await service.delete(session, tenant_id, matches[0])
            await DatabaseAuditLog().append(
                session,
                tenant_id,
                AuditRecord(
                    action="budget.deleted",
                    outcome="ok",
                    resource_type="budget",
                    resource_id=str(matches[0]),
                ),
            )
            return matches[0]


@app.command("delete")
def delete(
    ctx: typer.Context,
    budget: Annotated[str, typer.Argument(help="Id of the budget, or its first characters.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Delete a budget."""
    typer.echo(f"Deleted budget {run(_delete(settings_from(ctx), tenant, budget))}.")
