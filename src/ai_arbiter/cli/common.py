"""What every command group shares: state, error reporting, database access."""

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import typer
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.core.audit import DatabaseAuditLog
from ai_arbiter.core.config.settings import Settings, load_settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.errors import ArbiterError, NotFoundError
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.core.plugins.registry import EVENT_BUSES, PluginRegistry
from ai_arbiter.gateway.identity.model import Principal, PrincipalKind

DISCLAIMER = "Arbiter is a support tool. It does not provide legal advice."


@dataclass
class CliState:
    config_file: Path | None = None


def fail(error: ArbiterError) -> typer.Exit:
    typer.echo(f"Error: {error}", err=True)
    return typer.Exit(code=1)


def settings_from(ctx: typer.Context) -> Settings:
    state: CliState = ctx.obj
    try:
        return load_settings(state.config_file)
    except ArbiterError as error:
        raise fail(error) from error


def run[T](coroutine: Coroutine[Any, Any, T]) -> T:
    """Run a command's coroutine; print Arbiter's own errors without a traceback."""
    try:
        return asyncio.run(coroutine)
    except ArbiterError as error:
        raise fail(error) from error
    except OperationalError as error:
        raise fail(
            ArbiterError("the database is not initialised or not reachable; run: arbiter init")
        ) from error


@asynccontextmanager
async def open_database(settings: Settings) -> AsyncIterator[Database]:
    database = Database(settings.database.url)
    try:
        yield database
    finally:
        await database.dispose()


async def tenant_id_for(database: Database, slug: str = LOCAL_TENANT_SLUG) -> UUID:
    async with database.session() as session:
        tenant_id = await session.scalar(select(Tenant.id).where(Tenant.slug == slug))
    if tenant_id is None:
        raise NotFoundError(f"tenant '{slug}' not found; run: arbiter init")
    return tenant_id


async def tenant_for(database: Database, slug: str = LOCAL_TENANT_SLUG) -> Tenant:
    async with database.session() as session:
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is None:
        raise NotFoundError(f"tenant '{slug}' not found; run: arbiter init")
    return tenant


def compliance_for(settings: Settings) -> ComplianceRuntime:
    """The compliance services as the command line uses them."""
    bus = PluginRegistry().load(EVENT_BUSES, settings.plugins.event_bus)()
    return build_compliance(settings, audit=DatabaseAuditLog(), bus=bus)


async def reviewer_for(session: AsyncSession, tenant_id: UUID, name: str) -> UUID:
    """The principal a review is recorded under: found by name, or created.

    Reviews and audit entries hold this identifier, not the name, so that erasing the
    name from the principal leaves them intact.
    """
    name = name.strip()
    if not name:
        raise ArbiterError("a review needs the name of the reviewer: --reviewer NAME")
    principal = await session.scalar(
        select(Principal).where(
            Principal.tenant_id == tenant_id,
            Principal.kind == PrincipalKind.USER.value,
            Principal.display_name == name,
        )
    )
    if principal is None:
        principal = Principal(tenant_id=tenant_id, kind=PrincipalKind.USER.value, display_name=name)
        session.add(principal)
        await session.flush()
    return principal.id
