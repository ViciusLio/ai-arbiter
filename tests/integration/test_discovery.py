"""Discovery of systems from traffic: candidates, their findings, the drafts (ADR-0042)."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from ai_arbiter.compliance.findings.model import Finding
from ai_arbiter.compliance.inventory.declarations import (
    SystemDeclaration,
    load_declarations,
    parse_declarations,
)
from ai_arbiter.compliance.inventory.discovery import (
    discover,
    draft_declaration,
    ungrouped_requests,
)
from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.core.audit import DatabaseAuditLog
from ai_arbiter.core.config import load_settings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.rules import packaged_versions
from tests.integration.test_cli_compliance import arbiter, workspace
from tests.integration.test_compliance import EXAMPLES, NOW, FixedClock, declare, scan

SINCE = NOW - timedelta(days=30)
CANDIDATE_RULE = "SCAN-UNDECLARED-SYSTEM-CANDIDATE"
UNGROUPED_RULE = "SCAN-UNATTRIBUTED-TRAFFIC"
HR, SALES = new_id(), new_id()


@pytest.fixture
def compliance() -> ComplianceRuntime:
    clock = FixedClock()
    return build_compliance(
        load_settings(), audit=DatabaseAuditLog(clock), bus=InProcessEventBus(), clock=clock
    )


@pytest.fixture
def declarations() -> dict[str, SystemDeclaration]:
    return {system.key: system for system in load_declarations(EXAMPLES)}


async def traffic(
    database: Database,
    tenant_id: UUID,
    *,
    count: int = 1,
    project_id: UUID | None = None,
    source: str = "native",
    group: str | None = None,
    system_id: UUID | None = None,
    model: str = "gpt-4o",
    provider: str | None = "azure_openai",
    pii: tuple[str, ...] = (),
    at: datetime = NOW - timedelta(days=1),
) -> None:
    async with database.transaction() as session:
        for _ in range(count):
            identifier = new_id()
            session.add(
                Interaction(
                    id=identifier,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    ai_system_id=system_id,
                    source=source,
                    source_group=group,
                    source_record_id=str(identifier),
                    started_at=at,
                    status="ok",
                    requested_model=model,
                    model=model,
                    provider=provider,
                    pii_categories=list(pii),
                )
            )


async def candidate_findings(database: Database, tenant_id: UUID) -> list[Finding]:
    async with database.session() as session:
        rows = await session.scalars(
            select(Finding)
            .where(Finding.tenant_id == tenant_id, Finding.rule_id == CANDIDATE_RULE)
            .order_by(Finding.first_seen, Finding.id)
        )
        return list(rows.all())


async def test_candidates_are_projects_and_groups_of_a_source_with_what_they_used(
    database: Database, tenant_id: UUID
) -> None:
    await traffic(database, tenant_id, count=3, project_id=HR, pii=("email",))
    await traffic(database, tenant_id, count=2, project_id=HR, model="gpt-4o-mini")
    await traffic(database, tenant_id, count=4, source="litellm", group="sales", provider=None)
    await traffic(database, tenant_id, count=1, source="litellm", group="support")
    await traffic(database, tenant_id, count=6, source="litellm")
    await traffic(database, tenant_id, count=9, project_id=SALES, at=NOW - timedelta(days=40))

    async with database.session() as session:
        found = await discover(session, tenant_id, SINCE)
        rest = await ungrouped_requests(session, tenant_id, SINCE)

    assert [(item.reference, item.requests) for item in found] == [
        (f"project:{HR}", 5),
        ("source:litellm:sales", 4),
        ("source:litellm:support", 1),
    ]
    hr, sales, _ = found
    assert (hr.kind, hr.models, hr.pii_categories) == (
        "project",
        ["gpt-4o", "gpt-4o-mini"],
        ["email"],
    )
    assert hr.uses == [("azure_openai", "gpt-4o"), ("azure_openai", "gpt-4o-mini")]
    assert (sales.kind, sales.providers, sales.uses) == ("source", [], [("unknown", "gpt-4o")])
    assert sales.suggested_key == "discovered-litellm-sales"
    assert hr.suggested_key == f"discovered-{HR.hex[-8:]}"
    assert rest == 6


async def test_traffic_of_a_declared_system_or_of_another_tenant_is_not_a_candidate(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    other_tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")
    async with database.session() as session:
        system = await compliance.inventory.get(session, tenant_id, "cv-screening")
    await traffic(database, tenant_id, count=2, project_id=HR, system_id=system.id)
    await traffic(database, other_tenant_id, count=2, project_id=SALES)

    async with database.session() as session:
        mine = await discover(session, tenant_id, SINCE)
        theirs = await discover(session, other_tenant_id, SINCE)

    assert mine == []
    assert [item.reference for item in theirs] == [f"project:{SALES}"]


async def test_a_scan_reports_one_finding_per_candidate_and_keeps_it_across_scans(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    await traffic(database, tenant_id, count=3, project_id=HR)
    await traffic(database, tenant_id, count=2, source="litellm", group="sales")
    await traffic(database, tenant_id, count=1, source="litellm")

    first = await scan(compliance, database, tenant_id)
    await traffic(database, tenant_id, count=4, project_id=HR, model="gpt-4o-mini")
    second = await scan(compliance, database, tenant_id)

    findings = await candidate_findings(database, tenant_id)
    assert (first["candidates"], second["candidates"]) == (2, 2)
    assert [(f.severity, f.status, f.occurrences, f.ai_system_id) for f in findings] == [
        ("medium", "open", 2, None),
        ("medium", "open", 2, None),
    ]
    assert len({finding.fingerprint for finding in findings}) == 2
    async with database.session() as session:
        details = [
            await compliance.findings.get(session, tenant_id, finding.id) for finding in findings
        ]
        ungrouped = (
            await session.scalars(select(Finding).where(Finding.rule_id == UNGROUPED_RULE))
        ).one()
        evidence = (await compliance.findings.get(session, tenant_id, ungrouped.id)).evidence
    observed = {
        detail.evidence[-1].data["candidate"]: detail.evidence[-1].data for detail in details
    }
    assert observed[f"project:{HR}"]["requests"] == 7
    assert observed[f"project:{HR}"]["models"] == ["gpt-4o", "gpt-4o-mini"]
    assert observed["source:litellm:sales"]["requests"] == 2
    assert evidence[-1].data["requests"] == 1


async def test_declaring_the_project_closes_the_candidate_and_counts_its_traffic(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await traffic(database, tenant_id, count=3, project_id=HR, model="other-model")
    await scan(compliance, database, tenant_id)
    async with database.session() as session:
        (candidate,) = await discover(session, tenant_id, SINCE)
    draft = draft_declaration(candidate, "HR assistant")
    (parsed,) = parse_declarations(json.dumps({"systems": [draft]}))

    await declare(compliance, database, tenant_id, {parsed.key: parsed})
    await scan(compliance, database, tenant_id)

    assert (parsed.projects(), parsed.facts, parsed.roles) == ((HR,), {}, [])
    assert [(m.provider, m.model) for m in parsed.models] == [("azure_openai", "other-model")]
    (finding,) = await candidate_findings(database, tenant_id)
    assert finding.status == "mitigated"
    async with database.session() as session:
        assert await discover(session, tenant_id, SINCE) == []
        system = await compliance.inventory.get(session, tenant_id, parsed.key)
        _, observed = await compliance.scanner.observe(session, system)
        current = await compliance.classifier.current(session, tenant_id, system.id)
    assert observed["requests"] == 3
    assert current is not None
    # A draft answers no question, so nothing is read as "no".
    assert current.tier.value == "undetermined"


async def test_a_scan_pack_from_before_discovery_reports_all_such_traffic_as_one_finding(
    database: Database, tenant_id: UUID, tmp_path: Path
) -> None:
    from importlib import resources

    old = resources.files("ai_arbiter.rulepacks").joinpath("scan", "2026.10.0", "pack.yaml")
    path = tmp_path / "pack.yaml"
    path.write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
    clock = FixedClock()
    compliance = build_compliance(
        load_settings(compliance={"scan_pack": str(path)}),
        audit=DatabaseAuditLog(clock),
        bus=InProcessEventBus(),
        clock=clock,
    )
    await traffic(database, tenant_id, count=3, project_id=HR)
    await traffic(database, tenant_id, count=1, source="litellm")

    stats = await scan(compliance, database, tenant_id)

    assert packaged_versions("scan")[:2] == ["2026.10.0", "2026.10.1"]
    assert stats["candidates"] == 0
    assert await candidate_findings(database, tenant_id) == []
    async with database.session() as session:
        finding = (await session.scalars(select(Finding))).one()
        detail = await compliance.findings.get(session, tenant_id, finding.id)
    assert (finding.rule_id, detail.evidence[-1].data["requests"]) == (UNGROUPED_RULE, 4)


# --- command line ------------------------------------------------------------------------


def records(path: Path) -> None:
    now = datetime.now(UTC)
    lines = [
        {
            "source": "other-gateway",
            "source_record_id": f"r-{number}",
            "started_at": (now - timedelta(hours=number)).isoformat(),
            "model": "gpt-4o",
            "provider": "azure_openai",
            "group": group,
        }
        for number, group in enumerate(["careers-site", "careers-site", "help-desk", None], 1)
    ]
    for line in lines:
        if line["group"] is None:
            del line["group"]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")


def test_discover_lists_candidates_and_says_when_there_are_none(tmp_path: Path) -> None:
    workspace()
    empty = arbiter("systems", "discover")
    records(tmp_path / "records.jsonl")
    arbiter("ingest", str(tmp_path / "records.jsonl"))

    english = arbiter("systems", "discover")
    italian = arbiter("systems", "discover", "--locale", "it")

    assert "No candidate: every request of the last 30 days belongs to a declared system." in empty
    assert "2 candidate systems in the traffic of the last 30 days." in english
    lines = [line.split() for line in english.splitlines() if line.startswith("source:")]
    assert [(line[0], line[1], line[2]) for line in lines] == [
        ("source:other-gateway:careers-site", "careers-site", "2"),
        ("source:other-gateway:help-desk", "help-desk", "1"),
    ]
    assert "1 more requests are tied to no declared system and cannot be grouped." in english
    assert "It does not provide legal advice." in english
    assert "2 sistemi candidati nel traffico degli ultimi 30 giorni." in italian
    assert "Error: " in arbiter("systems", "discover", "--draft", "--tenant", "nobody", ok=False)


def test_a_draft_is_a_declaration_a_person_completes_and_applies(tmp_path: Path) -> None:
    workspace()
    arbiter("keys", "create", "--name", "demo")
    records(tmp_path / "records.jsonl")
    arbiter("ingest", str(tmp_path / "records.jsonl"))
    connection = sqlite3.connect(tmp_path / ".arbiter" / "arbiter.db")
    try:
        # As if the first two requests had come through the gateway with the demo key.
        connection.execute(
            "UPDATE interaction SET source = 'native', source_group = NULL, "
            "project_id = (SELECT project_id FROM api_key LIMIT 1) "
            "WHERE source_group = 'careers-site'"
        )
        connection.commit()
    finally:
        connection.close()

    listed = arbiter("systems", "discover")
    draft = arbiter("systems", "discover", "--draft")
    (tmp_path / "draft.yaml").write_text(draft, encoding="utf-8")
    applied = arbiter("systems", "apply", "-f", str(tmp_path / "draft.yaml"))
    after = arbiter("systems", "discover")

    project_line = next(line for line in listed.splitlines() if line.startswith("project:"))
    assert " / " in project_line
    assert draft.startswith("# Drafts from the traffic of the last 30 days.")
    assert "arbiter keys create --system KEY" in draft
    assert "ingest.mappings" in draft
    assert "facts: {}" in draft
    assert applied.count("created") == 2
    assert "undetermined" in applied
    # The project is now accounted for; the imported group stays until it is mapped.
    assert "1 candidate systems" in after
    assert "source:other-gateway:help-desk" in after
    assert "project:" not in after
    assert "Error: No candidate" not in arbiter("systems", "discover", "--draft")
