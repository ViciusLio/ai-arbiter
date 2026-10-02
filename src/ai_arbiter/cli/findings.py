"""``arbiter scan`` and ``arbiter findings``: detect, then let a person decide."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import typer
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.cli.common import (
    compliance_for,
    open_database,
    reviewer_for,
    run,
    settings_from,
    tenant_id_for,
)
from ai_arbiter.cli.systems import Locale, TenantSlug, translator
from ai_arbiter.compliance.findings.model import (
    SEVERITY_ORDER,
    Finding,
    FindingStatus,
    SuppressionScope,
)
from ai_arbiter.compliance.findings.service import ACTIVE
from ai_arbiter.compliance.runtime import ComplianceRuntime
from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.domain.tenancy import LOCAL_TENANT_SLUG
from ai_arbiter.core.errors import ConflictError, NotFoundError

app = typer.Typer(help="Review what the scanner found.", no_args_is_help=True)


async def _scan(settings: Settings, tenant: str) -> dict[str, Any]:
    compliance = compliance_for(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            return dict((await compliance.scanner.run(session, tenant_id)).stats)


def scan(ctx: typer.Context, tenant: TenantSlug = LOCAL_TENANT_SLUG) -> None:
    """Scan the inventory and the traffic of the last 30 days, and report findings."""
    stats = run(_scan(settings_from(ctx), tenant))
    typer.echo(f"Scanned {stats['systems']} systems: {stats['detections']} detections.")
    for name in ("opened", "refreshed", "reopened", "unchanged", "suppressed", "mitigated"):
        if stats.get(name):
            typer.echo(f"  {name}: {stats[name]}")
    typer.echo("Findings are proposals until a person reviews them: arbiter findings list")


def short(finding_id: UUID) -> str:
    """The last characters of an id: its first ones are a timestamp shared by a scan."""
    return finding_id.hex[-8:]


async def _resolve(
    compliance: ComplianceRuntime, session: AsyncSession, tenant_id: UUID, reference: str
) -> Finding:
    """A finding by its full id or by the short id shown in lists."""
    findings = await compliance.findings.list(session, tenant_id)
    matches = [f for f in findings if str(f.id) == reference or short(f.id) == reference.lower()]
    if not matches:
        raise NotFoundError(f"finding '{reference}' not found")
    if len(matches) > 1:
        raise ConflictError(f"'{reference}' matches several findings: use the full id")
    return matches[0]


async def _list(settings: Settings, tenant: str, statuses: list[str], locale: str) -> list[str]:
    t = translator(locale)
    compliance = compliance_for(settings)
    rank = {severity.value: position for position, severity in enumerate(SEVERITY_ORDER)}
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            keys = {s.id: s.key for s in await compliance.inventory.list(session, tenant_id)}
            findings = await compliance.findings.list(session, tenant_id, statuses=statuses or None)
    lines = []
    for finding in sorted(findings, key=lambda f: (rank.get(f.severity, 99), f.rule_id)):
        system = keys.get(finding.ai_system_id, "-") if finding.ai_system_id else "-"
        lines.append(
            f"{short(finding.id)}  {t.text('severity.' + finding.severity):<12} "
            f"{finding.status:<15} {system:<28} {t.text(finding.message_key)}"
        )
    return lines


@app.command("list")
def list_findings(
    ctx: typer.Context,
    status: Annotated[
        list[FindingStatus] | None,
        typer.Option("--status", help="Only these statuses. Repeatable."),
    ] = None,
    everything: Annotated[bool, typer.Option("--all", help="Include closed findings.")] = False,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
    locale: Locale = "en",
) -> None:
    """List findings, most severe first. Active ones only, unless asked otherwise."""
    statuses = [item.value for item in status] if status else ([] if everything else list(ACTIVE))
    lines = run(_list(settings_from(ctx), tenant, statuses, locale))
    if not lines:
        typer.echo("No findings.")
        return
    for line in lines:
        typer.echo(line)


async def _show(settings: Settings, tenant: str, reference: str, locale: str) -> list[str]:
    t = translator(locale)
    compliance = compliance_for(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.session() as session:
            finding = await _resolve(compliance, session, tenant_id, reference)
            detail = await compliance.findings.get(session, tenant_id, finding.id)
            system = (
                (await compliance.inventory.get_by_id(session, tenant_id, finding.ai_system_id)).key
                if finding.ai_system_id
                else "-"
            )
    refs = ", ".join(f"{ref.get('regulation')} {ref.get('article')}" for ref in finding.legal_refs)
    out = [
        f"{finding.id}",
        f"  {t.text(finding.message_key)}",
        f"  rule:      {finding.rule_id} ({finding.rulepack_version})",
        f"  system:    {system}",
        f"  severity:  {t.text('severity.' + finding.severity)}",
        f"  status:    {finding.status}",
        f"  reference: {refs or '-'}",
        f"  applies:   {finding.applies_from or '-'}",
        f"  seen:      {finding.occurrences} times, first {finding.first_seen:%Y-%m-%d}, "
        f"last {finding.last_seen:%Y-%m-%d}",
    ]
    if finding.accepted_until:
        out.append(f"  accepted until {finding.accepted_until}")
    for evidence in detail.evidence:
        out.append("  evidence:")
        out += [f"    {name}: {value}" for name, value in sorted(evidence.data.items())]
    if detail.reviews:
        out.append("  history:")
        for item in detail.reviews:
            who = "a reviewer" if item.reviewer_id else "the scanner"
            reason = f": {item.reason}" if item.reason else ""
            out.append(
                f"    {item.created_at:%Y-%m-%d} {item.from_status} -> {item.to_status} "
                f"by {who}{reason}"
            )
    return [*out, "", t.text("digest.indicative_note"), t.text("disclaimer")]


@app.command("show")
def show(
    ctx: typer.Context,
    finding: Annotated[str, typer.Argument(help="Finding id, full or short.")],
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
    locale: Locale = "en",
) -> None:
    """Show a finding with its evidence and its history."""
    for line in run(_show(settings_from(ctx), tenant, finding, locale)):
        typer.echo(line)


async def _review(
    settings: Settings,
    tenant: str,
    reference: str,
    to: FindingStatus,
    reviewer: str,
    reason: str,
    until: datetime | None,
    suppress: SuppressionScope | None,
) -> Finding:
    compliance = compliance_for(settings)
    async with open_database(settings) as database:
        tenant_id = await tenant_id_for(database, tenant)
        async with database.transaction() as session:
            finding = await _resolve(compliance, session, tenant_id, reference)
            return await compliance.findings.transition(
                session,
                tenant_id,
                finding.id,
                to,
                reviewer_id=await reviewer_for(session, tenant_id, reviewer),
                reason=reason,
                accepted_until=until.date() if until else None,
                suppress=suppress,
            )


@app.command("review")
def review(
    ctx: typer.Context,
    finding: Annotated[str, typer.Argument(help="Finding id, full or short.")],
    to: Annotated[FindingStatus, typer.Option("--to", help="The new status.")],
    reviewer: Annotated[str, typer.Option("--reviewer", help="Name of the person who decides.")],
    reason: Annotated[
        str, typer.Option("--reason", help="Why. Required to reject or accept.")
    ] = "",
    until: Annotated[
        datetime | None,
        typer.Option("--until", formats=["%Y-%m-%d"], help="Expiry of an accepted risk."),
    ] = None,
    suppress: Annotated[
        SuppressionScope | None,
        typer.Option("--suppress", help="With false_positive: stop the rule for this scope."),
    ] = None,
    tenant: TenantSlug = LOCAL_TENANT_SLUG,
) -> None:
    """Change the status of a finding: confirmed, false_positive, accepted, mitigated, open."""
    updated = run(
        _review(settings_from(ctx), tenant, finding, to, reviewer, reason, until, suppress)
    )
    typer.echo(f"{short(updated.id)}: {updated.status} by {reviewer}")
