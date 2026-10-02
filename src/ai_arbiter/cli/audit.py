"""``arbiter audit``: verify and export the audit chain."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from ai_arbiter.cli.common import open_database, run, settings_from, tenant_id_for
from ai_arbiter.core.audit import DatabaseAuditLog, VerificationReport, verify_export
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG

app = typer.Typer(help="Verify and export the audit log.", no_args_is_help=True)

TenantSlug = Annotated[str, typer.Option("--tenant", help="Tenant slug.")]


def _report(report: VerificationReport) -> None:
    if report.ok:
        typer.echo(f"Audit chain verified: {report.entries} entries, no broken link.")
        if report.head_hash:
            typer.echo(f"Head: entry {report.head_seq}, hash {report.head_hash}")
        return
    typer.echo(
        f"Audit chain BROKEN at entry {report.first_broken_seq}: {report.problem}. "
        f"{report.entries} entries before it are sound.",
        err=True,
    )
    raise typer.Exit(code=1)


async def _verify(settings: Settings, tenant: str) -> VerificationReport:
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            return await DatabaseAuditLog().verify(session, tenant_id)


@app.command("verify")
def verify(
    ctx: typer.Context,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
    file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Verify an export file instead of the database."),
    ] = None,
) -> None:
    """Recompute the hash chain and report the first broken link.

    A chain that verifies is internally consistent. That is evidence against partial
    changes, not proof that the whole chain was never rewritten.
    """
    if file is not None:
        if not file.is_file():
            typer.echo(f"Error: file not found: {file}", err=True)
            raise typer.Exit(code=1)
        with file.open(encoding="utf-8") as lines:
            _report(verify_export(lines))
        return
    _report(run(_verify(settings_from(ctx), tenant)))


async def _export(settings: Settings, tenant: str, output: Path | None) -> int:
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        target = sys.stdout if output is None else output.open("w", encoding="utf-8", newline="\n")
        count = 0
        try:
            async with database.session() as session:
                async for line in DatabaseAuditLog().export(session, tenant_id):
                    target.write(line + "\n")
                    count += 1
        finally:
            if output is not None:
                target.close()
        return count - 2


@app.command("export")
def export(
    ctx: typer.Context,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="File to write. Default: standard output.")
    ] = None,
) -> None:
    """Write the audit chain as JSON lines that can be verified elsewhere."""
    entries = run(_export(settings_from(ctx), tenant, output))
    if output is not None:
        typer.echo(f"Exported {entries} entries to {output}")
