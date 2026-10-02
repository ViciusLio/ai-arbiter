"""``arbiter digest``, ``arbiter worker`` and ``arbiter retention``."""

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import typer

from ai_arbiter.cli.common import (
    compliance_for,
    fail,
    open_database,
    run,
    settings_from,
    tenant_for,
)
from ai_arbiter.cli.systems import TenantSlug
from ai_arbiter.compliance.digest.model import build_digest, record_digest_run
from ai_arbiter.compliance.digest.render import DigestFormat, render_digest
from ai_arbiter.compliance.ingest.service import IngestReport, IngestService
from ai_arbiter.compliance.retention import PurgeReport, purge
from ai_arbiter.compliance.worker import register_handlers
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.i18n import SUPPORTED_LOCALES
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.core.plugins.registry import PII_DETECTORS, TELEMETRY_SOURCES, PluginRegistry
from ai_arbiter.gateway.finops.catalogue import load_catalogue
from ai_arbiter.gateway.finops.metering import UsageMeter


async def _ingest(
    settings: Settings, tenant: str, path: Path, source_name: str, strict: bool
) -> IngestReport:
    registry = PluginRegistry()
    detector = registry.load(PII_DETECTORS, settings.plugins.pii_detector)()
    source = registry.load(TELEMETRY_SOURCES, source_name)(detector)
    compliance = compliance_for(settings)
    # Imported records are counted in the usage roll-ups like the gateway's own.
    meter = UsageMeter(load_catalogue(settings.finops))
    service = IngestService(compliance.audit, settings.ingest.mappings, sink=meter.record)
    async with open_database(settings) as database:
        row = await tenant_for(database, tenant)
        async with database.transaction() as session:
            with path.open(encoding="utf-8") as lines:
                return await service.ingest(session, row.id, lines, source, strict=strict)


def ingest(
    ctx: typer.Context,
    file: Annotated[Path, typer.Argument(help="File with one JSON record per line.")],
    source: Annotated[str, typer.Option(help="Format of the file: jsonl or litellm.")] = "jsonl",
    strict: Annotated[
        bool, typer.Option("--strict", help="Stop at the first record that cannot be read.")
    ] = False,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Import interaction records of another gateway. Content is dropped on the way in.

    Safe to repeat: records already imported are skipped. A record is attributed to a
    declared system by a tag of the source, or by a mapping in the configuration.
    """
    if not file.is_file():
        raise fail(ArbiterError(f"file not found: {file}"))
    report = run(_ingest(settings_from(ctx), tenant, file, source, strict))
    typer.echo(
        f"Read {report.read} records from {report.source}: {report.imported} imported, "
        f"{report.duplicates} already imported, {report.invalid} not readable."
    )
    for key, count in sorted(report.attributed.items()):
        typer.echo(f"  {count} attributed to {key}")
    if report.unattributed:
        typer.echo(f"  {report.unattributed} attributed to no declared system")
    for key in sorted(report.unknown_systems):
        typer.echo(f"  system '{key}' is named by records and is not declared")
    if report.invalid_lines:
        lines = ", ".join(str(number) for number in report.invalid_lines)
        more = " and more" if report.invalid > len(report.invalid_lines) else ""
        typer.echo(f"  not readable: lines {lines}{more}")


digest_app = typer.Typer(help="Build the daily digest.", no_args_is_help=True)
retention_app = typer.Typer(help="Apply the retention periods.", no_args_is_help=True)

_EXTENSION: dict[DigestFormat, str] = {"markdown": "md", "html": "html"}


async def _digest(
    settings: Settings, tenant: str, days: int, locales: list[str], formats: list[DigestFormat]
) -> dict[tuple[str, DigestFormat], str]:
    compliance = compliance_for(settings)
    now = utcnow()
    async with open_database(settings) as database:
        row = await tenant_for(database, tenant)
        async with database.transaction() as session:
            model = await build_digest(
                session,
                await session.get_one(Tenant, row.id),
                classifier=compliance.classifier,
                findings=compliance.findings,
                period_start=now - timedelta(days=days),
                period_end=now,
                generated_at=now,
            )
            await record_digest_run(session, row, model, locales)
    return {
        (locale, output): render_digest(model, locale=locale, output=output)
        for locale in locales
        for output in formats
    }


@digest_app.command("run")
def digest_run(
    ctx: typer.Context,
    locale: Annotated[str, typer.Option(help="Language: en, it or all.")] = "en",
    output_format: Annotated[
        str, typer.Option("--format", help="markdown, html or both.")
    ] = "markdown",
    days: Annotated[int, typer.Option(min=1, help="Length of the period, in days.")] = 1,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", "-o", help="Directory to write to. Default: standard output."),
    ] = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Build the digest of the last day: inventory, findings, traffic, audit head.

    Scheduling is external: run this from cron or from a container job.
    """
    locales = list(SUPPORTED_LOCALES) if locale == "all" else [locale]
    if not set(locales) <= set(SUPPORTED_LOCALES):
        raise fail(ArbiterError(f"unsupported locale '{locale}': use en, it or all"))
    formats: list[DigestFormat]
    if output_format == "both":
        formats = ["markdown", "html"]
    elif output_format in ("markdown", "html"):
        formats = [output_format]  # type: ignore[list-item]
    else:
        raise fail(
            ArbiterError(f"unsupported format '{output_format}': use markdown, html or both")
        )
    if output_dir is None and len(locales) * len(formats) > 1:
        raise fail(ArbiterError("several outputs need a directory: --output-dir DIR"))

    rendered = run(_digest(settings_from(ctx), tenant, days, locales, formats))
    if output_dir is None:
        typer.echo(next(iter(rendered.values())), nl=False)
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utcnow().strftime("%Y-%m-%d")
    for (language, kind), text in rendered.items():
        path = output_dir / f"digest-{stamp}.{language}.{_EXTENSION[kind]}"
        path.write_text(text, encoding="utf-8", newline="\n")
        typer.echo(f"Wrote {path}")


async def _work(settings: Settings, once: bool, interval: int) -> int:
    compliance = compliance_for(settings)
    bus = compliance.bus
    if not isinstance(bus, InProcessEventBus):
        raise ArbiterError("arbiter worker dispatches the in-process event bus only")
    total = 0
    async with open_database(settings) as database:
        register_handlers(bus, database, compliance)
        while True:
            result = await bus.dispatch_pending(database)
            total += result.delivered
            if result.delivered or result.failed:
                typer.echo(f"delivered {result.delivered}, failed {result.failed}")
            if once and not result.delivered:
                return total
            if not once and not result.delivered:
                await asyncio.sleep(interval)


def worker(
    ctx: typer.Context,
    once: Annotated[bool, typer.Option("--once", help="Deliver what is pending and exit.")] = False,
    interval: Annotated[int, typer.Option(min=1, help="Seconds to wait when idle.")] = 5,
) -> None:
    """Deliver pending events: a system is classified when it is declared or changed."""
    total = run(_work(settings_from(ctx), once, interval))
    typer.echo(f"Delivered {total} events.")


async def _purge(settings: Settings, tenant: str, dry_run: bool) -> PurgeReport:
    compliance = compliance_for(settings)
    async with open_database(settings) as database:
        row = await tenant_for(database, tenant)
        async with database.transaction() as session:
            return await purge(
                session,
                await session.get_one(Tenant, row.id),
                settings=settings.retention,
                classifier=compliance.classifier,
                audit=compliance.audit,
                now=utcnow(),
                dry_run=dry_run,
            )


@retention_app.command("purge")
def retention_purge(
    ctx: typer.Context,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Report without deleting.")] = False,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Delete interactions and dispatched events that are past their retention period.

    Interactions of high-risk systems are kept for at least six months. Audit entries
    and usage totals are never deleted.
    """
    report = run(_purge(settings_from(ctx), tenant, dry_run))
    verb = "Would delete" if report.dry_run else "Deleted"
    typer.echo(
        f"{verb} {report.interactions} interactions older than {report.interaction_months} "
        f"months (before {report.interaction_cutoff:%Y-%m-%d})."
    )
    if report.high_risk_systems:
        typer.echo(
            f"  {report.high_risk_systems} high-risk systems keep theirs until "
            f"{report.high_risk_cutoff:%Y-%m-%d} at least."
        )
    typer.echo(
        f"{verb} {report.outbox_events} dispatched events (before {report.outbox_cutoff:%Y-%m-%d})."
    )
