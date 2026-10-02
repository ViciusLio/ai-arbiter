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

from ai_arbiter.core.config.settings import Settings, load_settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.errors import ArbiterError, NotFoundError
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import Tenant

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
