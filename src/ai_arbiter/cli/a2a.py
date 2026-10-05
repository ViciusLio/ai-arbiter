"""``arbiter a2a``: the registry of A2A agents and who may call them."""

from typing import Annotated
from uuid import UUID

import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.cli.common import (
    fail,
    open_database,
    refers_to,
    run,
    settings_from,
    short_id,
    tenant_id_for,
)
from ai_arbiter.compliance.inventory.model import AISystem
from ai_arbiter.core.audit import AuditRecord, DatabaseAuditLog
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.errors import ArbiterError, NotFoundError
from ai_arbiter.core.plugins.registry import AGENT_CARD_READERS, PluginRegistry
from ai_arbiter.gateway.a2a.registry import A2aRegistry
from ai_arbiter.gateway.identity.model import ScopeType

app = typer.Typer(help="A2A agents: the registry and the allowlist.", no_args_is_help=True)
agents_app = typer.Typer(help="Register agents and read their cards.", no_args_is_help=True)
grants_app = typer.Typer(help="Who may call which agent.", no_args_is_help=True)
app.add_typer(agents_app, name="agents")
app.add_typer(grants_app, name="grants")

TenantSlug = Annotated[str, typer.Option("--tenant", help="Tenant slug.")]


def _registry(settings: Settings) -> A2aRegistry:
    reader = PluginRegistry().load(AGENT_CARD_READERS, settings.plugins.agent_card_reader)()
    return A2aRegistry(reader=reader, settings=settings.a2a)


async def _system_id(session: AsyncSession, tenant_id: UUID, key: str) -> UUID:
    found = await session.scalar(
        select(AISystem.id).where(AISystem.tenant_id == tenant_id, AISystem.key == key)
    )
    if found is None:
        raise NotFoundError(f"no system with key '{key}'")
    return found


async def _audit(
    session: AsyncSession, tenant_id: UUID, action: str, kind: str, identifier: UUID
) -> None:
    await DatabaseAuditLog().append(
        session,
        tenant_id,
        AuditRecord(action=action, outcome="ok", resource_type=kind, resource_id=str(identifier)),
    )


async def _add(
    settings: Settings,
    tenant: str,
    key: str,
    name: str,
    card_url: str,
    system: str | None,
    credential: str | None,
) -> None:
    registry = _registry(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            agent = await registry.register(
                session,
                tenant_id,
                key=key,
                name=name,
                card_url=card_url,
                ai_system_id=(
                    await _system_id(session, tenant_id, system) if system is not None else None
                ),
                credential=credential,
            )
            await _audit(session, tenant_id, "a2a_agent.registered", "a2a_agent", agent.id)


@agents_app.command("add")
def add_agent(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Name the registry knows the agent by.")],
    name: Annotated[str, typer.Option("--name", help="What the agent is, for people.")],
    card_url: Annotated[
        str,
        typer.Option(
            "--card-url", help="Where its Agent Card is: https://HOST/.well-known/agent-card.json"
        ),
    ],
    system: Annotated[
        str | None, typer.Option("--system", help="Key of the AI system it belongs to.")
    ] = None,
    credential: Annotated[
        str | None,
        typer.Option("--credential", help="secret://NAME of the credential sent to the agent."),
    ] = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Register an agent by the address of its card. The card is not read yet."""
    run(_add(settings_from(ctx), tenant, key, name, card_url, system, credential))
    typer.echo(f"Registered '{key}'. Its card was not read yet: arbiter a2a agents refresh {key}")
    typer.echo(f"No one may call it yet: arbiter a2a grants add {key}")


async def _list(settings: Settings, tenant: str) -> list[str]:
    registry = _registry(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            return [
                f"{agent.key:<24} {registry.governability(agent):<19} {agent.verification:<12} "
                f"{agent.card_name or '-'}"
                for agent in await registry.list(session, tenant_id)
            ]


@agents_app.command("list")
def list_agents(ctx: typer.Context, tenant: TenantSlug = LOCAL_TENANT_SLUG) -> None:
    """List the agents with what their card said and whether a proxy can govern each."""
    lines = run(_list(settings_from(ctx), tenant))
    if not lines:
        typer.echo("No agent is registered. Start with: arbiter a2a agents add")
        return
    for line in lines:
        typer.echo(line)


async def _refresh(settings: Settings, tenant: str, key: str) -> tuple[str, str, str | None, int]:
    registry = _registry(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        try:
            agent = await registry.refresh(database, DatabaseAuditLog(), tenant_id, key)
        finally:
            await registry.aclose()
    return (
        agent.verification,
        registry.governability(agent),
        agent.signing_key_id,
        len(registry.usable_interfaces(agent)),
    )


@agents_app.command("refresh")
def refresh_agent(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Key of the agent.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Read the Agent Card again and verify its signatures against the trusted keys.

    This makes one request, to the address of the card. A key the card names for itself
    is never fetched.
    """
    verification, state, kid, usable = run(_refresh(settings_from(ctx), tenant, key))
    signed = f" with the key '{kid}'" if kid else ""
    typer.echo(f"'{key}': the card is {verification}{signed}; the agent is {state}.")
    typer.echo(f"Interfaces a proxy can forward to: {usable}")


async def _remove(settings: Settings, tenant: str, key: str) -> None:
    registry = _registry(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            agent = await registry.remove(session, tenant_id, key)
            await _audit(session, tenant_id, "a2a_agent.removed", "a2a_agent", agent.id)


@agents_app.command("remove")
def remove_agent(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Key of the agent.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Remove an agent with its grants."""
    run(_remove(settings_from(ctx), tenant, key))
    typer.echo(f"Removed '{key}'.")


async def _grant(
    settings: Settings, tenant: str, key: str, project: UUID | None, system: str | None
) -> tuple[str, UUID]:
    registry = _registry(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            scope, scope_id = ScopeType.TENANT, None
            if project is not None:
                scope, scope_id = ScopeType.PROJECT, project
            elif system is not None:
                scope, scope_id = ScopeType.AI_SYSTEM, await _system_id(session, tenant_id, system)
            grant = await registry.grant(
                session, tenant_id, key, scope_type=scope, scope_id=scope_id
            )
            await _audit(session, tenant_id, "a2a_grant.created", "a2a_grant", grant.id)
            return scope.value, grant.id


@grants_app.command("add")
def add_grant(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Key of the agent.")],
    project: Annotated[
        UUID | None, typer.Option("--project", help="Identifier of the project allowed.")
    ] = None,
    system: Annotated[
        str | None, typer.Option("--system", help="Key of the AI system allowed.")
    ] = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Allow a project, an AI system or, with neither, the whole tenant to call an agent."""
    if project is not None and system is not None:
        raise fail(ArbiterError("use either --project or --system"))
    scope, grant_id = run(_grant(settings_from(ctx), tenant, key, project, system))
    typer.echo(f"{short_id(grant_id)}  {scope} may call '{key}'.")


async def _grants(settings: Settings, tenant: str, key: str | None) -> list[str]:
    registry = _registry(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            return [
                f"{short_id(grant.id)}  {agent:<24} {grant.scope_type:<10} {grant.scope_id}"
                for grant, agent in await registry.grants(session, tenant_id, key)
            ]


@grants_app.command("list")
def list_grants(
    ctx: typer.Context,
    key: Annotated[str | None, typer.Argument(help="Key of an agent. Default: all.")] = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """List who may call which agent."""
    lines = run(_grants(settings_from(ctx), tenant, key))
    if not lines:
        typer.echo("No grant: nobody may call an agent of the registry.")
        return
    for line in lines:
        typer.echo(line)


async def _revoke(settings: Settings, tenant: str, reference: str) -> UUID:
    registry = _registry(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            matches = [
                grant.id
                for grant, _ in await registry.grants(session, tenant_id)
                if refers_to(grant.id, reference)
            ]
            if len(matches) != 1:
                problem = "no grant" if not matches else "more than one grant"
                raise NotFoundError(f"{problem} with the id '{reference}'")
            await registry.revoke(session, tenant_id, matches[0])
            await _audit(session, tenant_id, "a2a_grant.revoked", "a2a_grant", matches[0])
            return matches[0]


@grants_app.command("remove")
def remove_grant(
    ctx: typer.Context,
    grant: Annotated[str, typer.Argument(help="Id of the grant, full or short.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Withdraw a grant. It takes effect at the next request."""
    typer.echo(f"Withdrew grant {run(_revoke(settings_from(ctx), tenant, grant))}.")
