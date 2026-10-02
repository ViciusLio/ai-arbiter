"""``arbiter keys``: issue, list and revoke API keys from the command line.

This is how the first key of a workspace comes to exist: the HTTP API needs a key to
create keys.
"""

from typing import Annotated

import typer
from sqlalchemy import select

from ai_arbiter.cli.common import open_database, run, settings_from, tenant_id_for
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG, AccessRole
from ai_arbiter.gateway.identity.keys import display_prefix
from ai_arbiter.gateway.identity.model import ApiKey, PrincipalKind, Project, Team
from ai_arbiter.gateway.runtime import build_runtime

app = typer.Typer(help="Manage API keys.", no_args_is_help=True)

TenantSlug = Annotated[str, typer.Option("--tenant", help="Tenant slug.")]


async def _create(
    settings: Settings, tenant: str, name: str, roles: list[AccessRole], team: str, project: str
) -> tuple[ApiKey, str]:
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        runtime = await build_runtime(settings, database)
        identity = runtime.identity
        async with database.transaction() as session:
            team_row = await session.scalar(
                select(Team).where(Team.tenant_id == tenant_id, Team.name == team)
            )
            if team_row is None:
                team_row = await identity.create_team(session, tenant_id, team)
            project_row = await session.scalar(
                select(Project).where(
                    Project.tenant_id == tenant_id,
                    Project.team_id == team_row.id,
                    Project.name == project,
                )
            )
            if project_row is None:
                project_row = await identity.create_project(
                    session, tenant_id, team_row.id, project
                )
            principal = await identity.create_principal(
                session, tenant_id, kind=PrincipalKind.SERVICE, display_name=name
            )
            for role in roles:
                await identity.grant_role(session, tenant_id, principal_id=principal.id, role=role)
            row, key = await identity.issue_api_key(
                session, tenant_id, project_id=project_row.id, principal_id=principal.id, name=name
            )
            await runtime.audit.append(
                session,
                tenant_id,
                AuditRecord(
                    action="api_key.issued",
                    outcome="ok",
                    resource_type="api_key",
                    resource_id=row.key_id,
                ),
            )
        await runtime.aclose()
        return row, key


@app.command("create")
def create(
    ctx: typer.Context,
    name: Annotated[str, typer.Option("--name", help="What the key is for.")],
    role: Annotated[
        list[AccessRole] | None,
        typer.Option("--role", help="Role on the tenant. Repeat for several. Default: developer."),
    ] = None,
    team: Annotated[str, typer.Option(help="Team, created if missing.")] = "default",
    project: Annotated[str, typer.Option(help="Project, created if missing.")] = "default",
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Issue a key for a new service principal. The key is shown once."""
    roles = role or [AccessRole.DEVELOPER]
    row, key = run(_create(settings_from(ctx), tenant, name, roles, team, project))
    typer.echo(f"Key id:  {row.key_id}")
    typer.echo(f"Roles:   {', '.join(sorted(item.value for item in roles))}")
    typer.echo(f"Project: {team}/{project}")
    typer.echo("")
    typer.echo(key)
    typer.echo("")
    typer.echo("Store it now: it is not kept and cannot be shown again.")


async def _list(settings: Settings, tenant: str) -> list[ApiKey]:
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            rows = await session.scalars(
                select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at)
            )
            return list(rows)


@app.command("list")
def list_keys(ctx: typer.Context, tenant: TenantSlug = LOCAL_TENANT_SLUG) -> None:
    """List keys by their public id. The keys themselves are not stored."""
    rows = run(_list(settings_from(ctx), tenant))
    if not rows:
        typer.echo("No API keys. Create one with: arbiter keys create --name NAME")
        return
    for row in rows:
        state = "revoked" if row.revoked_at else "active"
        typer.echo(
            f"{display_prefix(row.key_id)}  {state:<8} {row.created_at:%Y-%m-%d}  {row.name}"
        )


async def _revoke(settings: Settings, tenant: str, key_id: str) -> None:
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        runtime = await build_runtime(settings, database)
        async with database.transaction() as session:
            row = await runtime.identity.revoke_api_key(session, tenant_id, key_id)
            await runtime.audit.append(
                session,
                tenant_id,
                AuditRecord(
                    action="api_key.revoked",
                    outcome="ok",
                    resource_type="api_key",
                    resource_id=row.key_id,
                ),
            )
        await runtime.aclose()


@app.command("revoke")
def revoke(
    ctx: typer.Context,
    key_id: Annotated[str, typer.Argument(help="Key id, with or without the arb_ prefix.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Revoke a key. It stops working at once."""
    run(_revoke(settings_from(ctx), tenant, key_id.removeprefix("arb_")))
    typer.echo(f"Revoked {display_prefix(key_id.removeprefix('arb_'))}")
