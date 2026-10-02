"""What every command group shares: state, error reporting, database access."""

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import typer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.digest.render import DigestFormat
from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.core.audit import DatabaseAuditLog
from ai_arbiter.core.config.settings import Settings, load_settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.errors import ArbiterError, ConfigurationError, NotFoundError
from ai_arbiter.core.i18n import SUPPORTED_LOCALES
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.core.plugins.registry import (
    EVENT_BUSES,
    NOTIFIERS,
    SECRET_STORES,
    PluginRegistry,
)
from ai_arbiter.core.ports import Notifier
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


def notifier_for(settings: Settings) -> Notifier:
    """The notifier named in the configuration, with its settings checked.

    Raises ``PluginError`` for an unknown notifier and ``ConfigurationError`` for
    settings it rejects, before anything is sent.
    """
    registry = PluginRegistry()
    name = settings.plugins.notifier
    plugin = registry.load(NOTIFIERS, name)
    try:
        options = plugin.settings_model.model_validate(settings.notifications.settings)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'settings'}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError(
            f"notifications.settings: invalid settings for notifier '{name}': {problems}"
        ) from exc
    secrets = registry.load(SECRET_STORES, settings.plugins.secret_store)()
    notifier: Notifier = plugin(secrets, options)
    return notifier


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


_EXTENSION: dict[DigestFormat, str] = {"markdown": "md", "html": "html"}


def output_choices(
    locale: str, output_format: str, *, to_directory: bool
) -> tuple[list[str], list[DigestFormat]]:
    """The languages and formats asked for a digest or a report."""
    locales = list(SUPPORTED_LOCALES) if locale == "all" else [locale]
    if not set(locales) <= set(SUPPORTED_LOCALES):
        raise fail(ArbiterError(f"unsupported locale '{locale}': use en, it or all"))
    formats: list[DigestFormat]
    if output_format == "both":
        formats = ["markdown", "html"]
    elif output_format == "markdown":
        formats = ["markdown"]
    elif output_format == "html":
        formats = ["html"]
    else:
        raise fail(
            ArbiterError(f"unsupported format '{output_format}': use markdown, html or both")
        )
    if not to_directory and len(locales) * len(formats) > 1:
        raise fail(ArbiterError("several outputs need a directory: --output-dir DIR"))
    return locales, formats


def write_outputs(
    rendered: dict[tuple[str, DigestFormat], str], output_dir: Path | None, name: str
) -> None:
    """Print the only output, or write each as ``<name>-<date>.<locale>.<extension>``."""
    if output_dir is None:
        typer.echo(next(iter(rendered.values())), nl=False)
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y-%m-%d")
    for (language, kind), text in rendered.items():
        path = output_dir / f"{name}-{stamp}.{language}.{_EXTENSION[kind]}"
        path.write_text(text, encoding="utf-8", newline="\n")
        typer.echo(f"Wrote {path}")
