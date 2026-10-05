"""``arbiter mcp``: the catalogue of MCP servers and who may call them."""

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
from ai_arbiter.core.plugins.registry import SECRET_STORES, PluginRegistry
from ai_arbiter.core.ports import NoSystemDirectory
from ai_arbiter.gateway.identity.model import ScopeType
from ai_arbiter.gateway.mcp.catalogue import McpCatalogue, governability
from ai_arbiter.gateway.mcp.model import ANY_TOOL, McpTransport
from ai_arbiter.gateway.mcp.proxy import McpProxy, load_mcp_pack

app = typer.Typer(help="MCP servers: the catalogue and the allowlist.", no_args_is_help=True)
servers_app = typer.Typer(help="Register and list MCP servers.", no_args_is_help=True)
grants_app = typer.Typer(help="Who may call which server and tool.", no_args_is_help=True)
app.add_typer(servers_app, name="servers")
app.add_typer(grants_app, name="grants")

TenantSlug = Annotated[str, typer.Option("--tenant", help="Tenant slug.")]


def _catalogue(settings: Settings) -> McpCatalogue:
    return McpCatalogue(allow_http_hosts=settings.mcp.allow_http_hosts)


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
    url: str | None,
    stdio: bool,
    system: str | None,
    credential: str | None,
) -> str:
    catalogue = _catalogue(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            server = await catalogue.register(
                session,
                tenant_id,
                key=key,
                name=name,
                transport=McpTransport.STDIO if stdio else McpTransport.STREAMABLE_HTTP,
                url=url,
                ai_system_id=(
                    await _system_id(session, tenant_id, system) if system is not None else None
                ),
                credential=credential,
            )
            await _audit(session, tenant_id, "mcp_server.registered", "mcp_server", server.id)
            return governability(server)


@servers_app.command("add")
def add_server(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Name the proxy serves the server under.")],
    name: Annotated[str, typer.Option("--name", help="What the server is, for people.")],
    url: Annotated[str | None, typer.Option("--url", help="Its Streamable HTTP endpoint.")] = None,
    stdio: Annotated[
        bool, typer.Option("--stdio", help="A local server: declared, never proxied or started.")
    ] = False,
    system: Annotated[
        str | None, typer.Option("--system", help="Key of the AI system it belongs to.")
    ] = None,
    credential: Annotated[
        str | None,
        typer.Option("--credential", help="secret://NAME of the credential sent upstream."),
    ] = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Register an MCP server. Nobody may call it until a grant says so."""
    state = run(_add(settings_from(ctx), tenant, key, name, url, stdio, system, credential))
    typer.echo(f"Registered '{key}' ({state}).")
    typer.echo(f"No one may call it yet: arbiter mcp grants add {key}")


async def _list(settings: Settings, tenant: str) -> list[str]:
    catalogue = _catalogue(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            lines = []
            for server in await catalogue.list(session, tenant_id):
                tools = await catalogue.tools(session, server)
                lines.append(
                    f"{server.key:<24} {governability(server):<12} {server.transport:<16} "
                    f"{len(tools):>3} tools  {server.url or '-'}"
                )
            return lines


@servers_app.command("list")
def list_servers(ctx: typer.Context, tenant: TenantSlug = LOCAL_TENANT_SLUG) -> None:
    """List the servers of the catalogue and whether the proxy can govern each."""
    lines = run(_list(settings_from(ctx), tenant))
    if not lines:
        typer.echo("No MCP server is registered. Start with: arbiter mcp servers add")
        return
    for line in lines:
        typer.echo(line)


async def _refresh(settings: Settings, tenant: str, key: str) -> tuple[str, list[str], list[str]]:
    registry = PluginRegistry()
    catalogue = _catalogue(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        proxy = McpProxy(
            database=database,
            catalogue=catalogue,
            pack=load_mcp_pack(settings.mcp),
            audit=DatabaseAuditLog(),
            secrets=registry.load(SECRET_STORES, settings.plugins.secret_store)(),
            settings=settings.mcp,
            systems=NoSystemDirectory(),
        )
        try:
            server = await proxy.discover(tenant_id, key)
            async with database.session() as session:
                tools = list(await catalogue.tools(session, server))
        finally:
            await proxy.aclose()
    return governability(server), [str(v) for v in server.protocol_versions], tools


@servers_app.command("refresh")
def refresh_server(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Key of the server.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Ask a server which protocol revisions it speaks and which tools it lists.

    This makes requests to the URL of the server, with its credential if it has one.
    """
    state, versions, tools = run(_refresh(settings_from(ctx), tenant, key))
    typer.echo(f"'{key}' is {state}. Revisions: {', '.join(versions) or '-'}.")
    typer.echo(f"Tools: {', '.join(tools) or '-'}")


async def _remove(settings: Settings, tenant: str, key: str) -> None:
    catalogue = _catalogue(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            server = await catalogue.remove(session, tenant_id, key)
            await _audit(session, tenant_id, "mcp_server.removed", "mcp_server", server.id)


@servers_app.command("remove")
def remove_server(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Key of the server.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Remove a server with its tools and its grants."""
    run(_remove(settings_from(ctx), tenant, key))
    typer.echo(f"Removed '{key}'.")


async def _grant(
    settings: Settings,
    tenant: str,
    key: str,
    tool: str,
    project: UUID | None,
    system: str | None,
) -> tuple[str, UUID]:
    catalogue = _catalogue(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            scope, scope_id = ScopeType.TENANT, None
            if project is not None:
                scope, scope_id = ScopeType.PROJECT, project
            elif system is not None:
                scope, scope_id = ScopeType.AI_SYSTEM, await _system_id(session, tenant_id, system)
            grant = await catalogue.grant(
                session, tenant_id, key, scope_type=scope, scope_id=scope_id, tool=tool
            )
            await _audit(session, tenant_id, "mcp_grant.created", "mcp_grant", grant.id)
            return scope.value, grant.id


@grants_app.command("add")
def add_grant(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Key of the server.")],
    tool: Annotated[
        str, typer.Option("--tool", help="One tool. Default: every tool of the server.")
    ] = ANY_TOOL,
    project: Annotated[
        UUID | None, typer.Option("--project", help="Identifier of the project allowed.")
    ] = None,
    system: Annotated[
        str | None, typer.Option("--system", help="Key of the AI system allowed.")
    ] = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Allow a project, an AI system or, with neither, the whole tenant to call a server."""
    if project is not None and system is not None:
        raise fail(ArbiterError("use either --project or --system"))
    scope, grant_id = run(_grant(settings_from(ctx), tenant, key, tool, project, system))
    what = "every tool" if tool == ANY_TOOL else f"the tool '{tool}'"
    typer.echo(f"{short_id(grant_id)}  {scope} may call {what} of '{key}'.")


async def _grants(settings: Settings, tenant: str, key: str | None) -> list[str]:
    catalogue = _catalogue(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            return [
                f"{short_id(grant.id)}  {server:<24} {grant.scope_type:<10} "
                f"{grant.scope_id}  {grant.tool}"
                for grant, server in await catalogue.grants(session, tenant_id, key)
            ]


@grants_app.command("list")
def list_grants(
    ctx: typer.Context,
    key: Annotated[str | None, typer.Argument(help="Key of a server. Default: all.")] = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """List who may call what."""
    lines = run(_grants(settings_from(ctx), tenant, key))
    if not lines:
        typer.echo("No grant: nobody may call an MCP server through the proxy.")
        return
    for line in lines:
        typer.echo(line)


async def _revoke(settings: Settings, tenant: str, reference: str) -> UUID:
    catalogue = _catalogue(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            matches = [
                grant.id
                for grant, _ in await catalogue.grants(session, tenant_id)
                if refers_to(grant.id, reference)
            ]
            if len(matches) != 1:
                problem = "no grant" if not matches else "more than one grant"
                raise NotFoundError(f"{problem} with the id '{reference}'")
            await catalogue.revoke(session, tenant_id, matches[0])
            await _audit(session, tenant_id, "mcp_grant.revoked", "mcp_grant", matches[0])
            return matches[0]


@grants_app.command("remove")
def remove_grant(
    ctx: typer.Context,
    grant: Annotated[str, typer.Argument(help="Id of the grant, full or short.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Withdraw a grant. It takes effect at the next request."""
    typer.echo(f"Withdrew grant {run(_revoke(settings_from(ctx), tenant, grant))}.")
