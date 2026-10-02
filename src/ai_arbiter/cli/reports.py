"""``arbiter report``: one system in full, and the audit log over a period."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

import typer

from ai_arbiter.cli.common import (
    compliance_for,
    fail,
    open_database,
    output_choices,
    run,
    settings_from,
    tenant_for,
    write_outputs,
)
from ai_arbiter.cli.systems import TenantSlug
from ai_arbiter.compliance.digest.render import DigestFormat
from ai_arbiter.compliance.reports.model import build_audit_report, build_system_report
from ai_arbiter.compliance.reports.render import render_audit_report, render_system_report
from ai_arbiter.core.audit import DatabaseAuditLog
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.persistence.tenant import Tenant

app = typer.Typer(help="Write reports for people outside the tool.", no_args_is_help=True)

Locale = Annotated[str, typer.Option(help="Language: en, it or all.")]
Format = Annotated[str, typer.Option("--format", help="markdown, html or both.")]
OutputDir = Annotated[
    Path | None,
    typer.Option("--output-dir", "-o", help="Directory to write to. Default: standard output."),
]

Rendered = dict[tuple[str, DigestFormat], str]


async def _system(
    settings: Settings, tenant: str, key: str, locales: list[str], formats: list[DigestFormat]
) -> Rendered:
    compliance = compliance_for(settings)
    async with open_database(settings) as database:
        row = await tenant_for(database, tenant)
        async with database.session() as session:
            report = await build_system_report(
                session, await session.get_one(Tenant, row.id), compliance, key
            )
    return {
        (locale, output): render_system_report(report, locale=locale, output=output)
        for locale in locales
        for output in formats
    }


@app.command("system")
def system_report(
    ctx: typer.Context,
    key: Annotated[str, typer.Argument(help="Key of the system.")],
    locale: Locale = "en",
    output_format: Format = "markdown",
    output_dir: OutputDir = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Everything recorded about one system: declaration, indicative classification with
    its obligations and dates, review, findings and traffic of the last 30 days.
    """
    locales, formats = output_choices(locale, output_format, to_directory=output_dir is not None)
    rendered = run(_system(settings_from(ctx), tenant, key, locales, formats))
    write_outputs(rendered, output_dir, f"report-system-{key}")


async def _audit(
    settings: Settings,
    tenant: str,
    start: datetime,
    end: datetime,
    locales: list[str],
    formats: list[DigestFormat],
) -> Rendered:
    async with open_database(settings) as database:
        row = await tenant_for(database, tenant)
        async with database.session() as session:
            report = await build_audit_report(
                session,
                await session.get_one(Tenant, row.id),
                DatabaseAuditLog(),
                period_start=start,
                period_end=end,
                generated_at=utcnow(),
            )
    return {
        (locale, output): render_audit_report(report, locale=locale, output=output)
        for locale in locales
        for output in formats
    }


@app.command("audit")
def audit_report(
    ctx: typer.Context,
    since: Annotated[
        datetime | None,
        typer.Option(formats=["%Y-%m-%d"], help="First day of the period, UTC."),
    ] = None,
    until: Annotated[
        datetime | None,
        typer.Option(formats=["%Y-%m-%d"], help="Last day of the period, UTC. Default: now."),
    ] = None,
    days: Annotated[
        int, typer.Option(min=1, help="Length of the period when --since is not given.")
    ] = 30,
    locale: Locale = "en",
    output_format: Format = "markdown",
    output_dir: OutputDir = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Whether the whole audit chain verifies, and what was recorded in a period.

    The chain is always recomputed from its first entry, whatever the period.
    """
    locales, formats = output_choices(locale, output_format, to_directory=output_dir is not None)
    end = utcnow() if until is None else until.replace(tzinfo=UTC) + timedelta(days=1)
    start = end - timedelta(days=days) if since is None else since.replace(tzinfo=UTC)
    if start >= end:
        raise fail(ArbiterError("the period is empty: --since is after --until"))
    rendered = run(_audit(settings_from(ctx), tenant, start, end, locales, formats))
    write_outputs(rendered, output_dir, "report-audit")
