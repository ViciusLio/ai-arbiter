"""The system report and the audit report: what they gather and how they read."""

from collections import Counter
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import update

from ai_arbiter.compliance.classifier.model import ReviewDecision
from ai_arbiter.compliance.inventory.declarations import SystemDeclaration, load_declarations
from ai_arbiter.compliance.reports import model as reports_model
from ai_arbiter.compliance.reports.model import (
    AuditReport,
    SystemReport,
    build_audit_report,
    build_system_report,
)
from ai_arbiter.compliance.reports.render import render_audit_report, render_system_report
from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.core.audit import AuditEntry, DatabaseAuditLog
from ai_arbiter.core.config import load_settings
from ai_arbiter.core.domain.risk import RiskTier
from ai_arbiter.core.errors import NotFoundError
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import Tenant
from tests.integration.test_compliance import (
    EXAMPLES,
    NOW,
    FixedClock,
    audit_actions,
    declare,
    interactions,
    review,
    scan,
)


@pytest.fixture
def compliance() -> ComplianceRuntime:
    clock = FixedClock()
    return build_compliance(
        load_settings(), audit=DatabaseAuditLog(clock), bus=InProcessEventBus(), clock=clock
    )


@pytest.fixture
def declarations() -> dict[str, SystemDeclaration]:
    return {system.key: system for system in load_declarations(EXAMPLES)}


async def system_report(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID, key: str
) -> SystemReport:
    async with database.session() as session:
        tenant = await session.get_one(Tenant, tenant_id)
        return await build_system_report(session, tenant, compliance, key)


async def audit_report(
    database: Database, tenant_id: UUID, *, days_ago: int = 0, days: int = 1
) -> AuditReport:
    end = NOW - timedelta(days=days_ago) + timedelta(seconds=1)
    async with database.session() as session:
        tenant = await session.get_one(Tenant, tenant_id)
        return await build_audit_report(
            session,
            tenant,
            DatabaseAuditLog(),
            period_start=end - timedelta(days=days),
            period_end=end,
            generated_at=NOW,
        )


# --- system report -----------------------------------------------------------------------


async def test_a_system_report_shows_classification_obligations_findings_and_traffic(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")
    await review(compliance, database, tenant_id, "cv-screening", ReviewDecision.CONFIRMED)
    async with database.session() as session:
        system = await compliance.inventory.get(session, tenant_id, "cv-screening")
    await interactions(database, tenant_id, system.id, count=2, model="other-model", pii=["email"])
    await scan(compliance, database, tenant_id)

    report = await system_report(compliance, database, tenant_id, "cv-screening")
    text = render_system_report(report)

    assert (report.tier, report.engine_tier, report.review_status) == (
        "high_risk",
        "high_risk",
        "confirmed",
    )
    assert text.startswith("# System report: CV screening\n")
    assert "\n\n\n" not in text
    assert "- **Key**: `cv-screening`" in text
    assert "- **AI Act roles**: deployer (Module of the HR suite bought from a vendor)" in text
    assert "- **Tier**: High-risk" in text
    assert "- **Review**: Confirmed by a reviewer" in text
    assert "Tier computed by the rules" not in text
    assert "| High-risk: recruitment or selection of persons (Annex III(4)(a)). |" in text
    assert "(readiness: not applicable yet)" in text
    assert "`SCAN-UNDECLARED-MODEL-IN-TRAFFIC`" in text
    assert "2 requests attributed to this system in the last 30 days." in text
    assert "Models in traffic that the declaration does not list: other-model." in text
    assert "Categories of personal data detected in prompts: email." in text
    assert "Classifications and findings are indicative." in text
    assert "its comparison with EUR-Lex by the project owner is still pending" in text
    assert text.rstrip().endswith("*Arbiter is a support tool. It does not provide legal advice.*")


async def test_a_system_report_keeps_the_engine_result_next_to_an_override(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "marketing-copy-generator")
    await review(
        compliance,
        database,
        tenant_id,
        "marketing-copy-generator",
        ReviewDecision.OVERRIDDEN,
        tier=RiskTier.TRANSPARENCY,
        reason="The generated text is published without editorial review.",
    )

    report = await system_report(compliance, database, tenant_id, "marketing-copy-generator")
    text = render_system_report(report)

    assert (report.tier, report.engine_tier) == ("transparency", "undetermined")
    assert "- **Tier**: Transparency obligations" in text
    assert "- **Review**: Set by a reviewer" in text
    assert "- **Tier computed by the rules**: Undetermined" in text
    assert (
        "- **Reason given by the reviewer**: The generated text is published without "
        "editorial review." in text
    )
    assert report.missing_facts
    assert "### Questions still to answer" in text
    assert f"(`{report.missing_facts[0]}`)" in text


async def test_a_system_report_of_an_unclassified_system_says_so(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening", classify=False)

    report = await system_report(compliance, database, tenant_id, "cv-screening")
    text = render_system_report(report)

    assert (report.tier, report.review_status) == (None, "not_classified")
    assert "The system is declared and has not been classified." in text
    assert "No findings." in text
    assert "0 requests attributed to this system in the last 30 days." in text


async def test_a_system_report_is_written_in_italian_and_escapes_html(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    named = declarations["cv-screening"].model_copy(update={"name": "CV <b>screening</b>"})
    await declare(compliance, database, tenant_id, {"cv-screening": named})
    await scan(compliance, database, tenant_id)

    report = await system_report(compliance, database, tenant_id, "cv-screening")
    markdown = render_system_report(report, locale="it")
    html = render_system_report(report, locale="it", output="html")

    assert markdown.startswith("# Report di sistema: CV <b>screening</b>\n")
    assert "- **Classe**: Alto rischio" in markdown
    assert "- **Revisione**: Indicativa, in attesa di revisione" in markdown
    assert '<html lang="it">' in html
    assert "<h1>Report di sistema: CV &lt;b&gt;screening&lt;/b&gt;</h1>" in html
    assert "<b>screening</b>" not in html
    assert "<footer>Arbiter" in html


async def test_a_system_report_of_another_tenant_or_an_unknown_key_is_not_found(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    other_tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")

    with pytest.raises(NotFoundError):
        await system_report(compliance, database, other_tenant_id, "cv-screening")
    with pytest.raises(NotFoundError):
        await system_report(compliance, database, tenant_id, "no-such-system")


# --- audit report ------------------------------------------------------------------------


async def test_an_audit_report_verifies_the_chain_and_counts_the_actions_of_the_period(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations)
    recorded = await audit_actions(database)

    report = await audit_report(database, tenant_id)
    text = render_audit_report(report)

    assert report.verification.ok
    assert report.total_in_period == len(recorded) == len(report.entries)
    assert dict(report.actions) == Counter(action for action, _ in recorded)
    assert not report.truncated
    assert text.startswith("# Audit report\n")
    assert "\n\n\n" not in text
    assert f"recomputed over all {len(recorded)} entries: no broken link." in text
    assert f"Head of the audit chain: entry {len(recorded)}, hash " in text
    assert "not proof that the whole chain was never rewritten" in text
    assert f"{len(recorded)} entries in the period." in text
    assert f"| `{recorded[0][0]}` |" in text
    assert "It does not provide legal advice." in text


async def test_an_audit_report_of_a_quiet_period_still_verifies_the_whole_chain(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")

    report = await audit_report(database, tenant_id, days_ago=10)
    text = render_audit_report(report, locale="it")

    assert report.total_in_period == 0
    assert report.verification.ok
    assert report.verification.entries > 0
    assert text.startswith("# Report di audit\n")
    assert "Nessuna voce di audit in questo periodo." in text
    assert "nessun anello rotto" in text


async def test_an_audit_report_lists_a_limited_number_of_entries_and_says_so(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reports_model, "MAX_AUDIT_ENTRIES", 3)
    await declare(compliance, database, tenant_id, declarations)

    report = await audit_report(database, tenant_id)
    html = render_audit_report(report, output="html")

    assert report.truncated
    assert [entry.seq for entry in report.entries] == [1, 2, 3]
    assert f"The first 3 of {report.total_in_period} entries are listed." in html
    assert "<h1>Audit report</h1>" in html


async def test_an_audit_report_says_where_the_chain_is_broken(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")
    async with database.transaction() as session:
        await session.execute(
            update(AuditEntry).where(AuditEntry.seq == 2).values(outcome="changed afterwards")
        )

    report = await audit_report(database, tenant_id)
    text = render_audit_report(report)

    assert not report.verification.ok
    assert report.verification.first_broken_seq == 2
    assert "**The chain is broken at entry 2: " in text
    assert "no broken link" not in text


async def test_an_audit_report_holds_the_entries_of_its_tenant_only(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    other_tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")

    report = await audit_report(database, other_tenant_id)

    assert report.total_in_period == 0
    assert report.verification.entries == 0
    assert "No audit entry in this period." in render_audit_report(report)
