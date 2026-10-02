"""``arbiter usage``: the usage report, from the local database."""

from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import select

from ai_arbiter.cli.common import fail, open_database, run, settings_from
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.errors import ArbiterError, NotFoundError
from ai_arbiter.core.i18n import SUPPORTED_LOCALES
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.gateway.finops.catalogue import load_catalogue
from ai_arbiter.gateway.finops.report import render_usage_report
from ai_arbiter.gateway.finops.usage import usage_report
from ai_arbiter.gateway.identity.model import ScopeType

app = typer.Typer(help="Usage and estimated cost.", no_args_is_help=True)


async def _report(
    settings: Settings, tenant: str, scope: ScopeType, start: date, end: date, locale: str
) -> str:
    catalogue = load_catalogue(settings.finops)
    async with open_database(settings) as database, database.session() as session:
        row = await session.scalar(select(Tenant).where(Tenant.slug == tenant))
        if row is None:
            raise NotFoundError(f"tenant '{tenant}' not found; run: arbiter init")
        report = await usage_report(
            session, row, scope, start=start, end=end, generated_at=utcnow()
        )
    return render_usage_report(
        report, catalogue, locale=locale, reporting=settings.finops.reporting
    )


@app.command("report")
def report(
    ctx: typer.Context,
    scope: Annotated[ScopeType, typer.Option(help="What to group by.")] = ScopeType.PROJECT,
    start: Annotated[
        datetime | None,
        typer.Option(
            "--from", formats=["%Y-%m-%d"], help="First day. Default: the 1st of the month."
        ),
    ] = None,
    end: Annotated[
        datetime | None,
        typer.Option("--to", formats=["%Y-%m-%d"], help="Last day. Default: today."),
    ] = None,
    locale: Annotated[str, typer.Option(help="Language: en or it.")] = "en",
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="File to write. Default: standard output.")
    ] = None,
    tenant: Annotated[str, typer.Option(help="Tenant slug.")] = LOCAL_TENANT_SLUG,
) -> None:
    """Write the usage report in Markdown. Costs are estimates, not invoices."""
    if locale not in SUPPORTED_LOCALES:
        raise fail(
            ArbiterError(f"unsupported locale '{locale}': use {' or '.join(SUPPORTED_LOCALES)}")
        )
    last = end.date() if end else utcnow().date()
    first = start.date() if start else last.replace(day=1)
    if first > last:
        raise fail(ArbiterError("--from is after --to"))
    text = run(_report(settings_from(ctx), tenant, scope, first, last, locale))
    if output is None:
        typer.echo(text, nl=False)
    else:
        output.write_text(text, encoding="utf-8", newline="\n")
        typer.echo(f"Wrote {output}")
