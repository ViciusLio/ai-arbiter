import json
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from ai_arbiter.compliance.ingest.service import IngestError, IngestService
from ai_arbiter.compliance.ingest.sources import JsonlSource, LiteLLMSource
from ai_arbiter.compliance.inventory.declarations import load_declarations
from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.core.audit import AuditEntry, DatabaseAuditLog
from ai_arbiter.core.config import IngestMapping, load_settings
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.redaction import BuiltinDetector
from ai_arbiter.gateway.finops.catalogue import load_catalogue
from ai_arbiter.gateway.finops.metering import UsageMeter
from ai_arbiter.gateway.finops.model import UsageRollup
from tests.support import text_in_database

EXAMPLES = Path(__file__).parents[2] / "examples"
LITELLM = (EXAMPLES / "litellm-logs.jsonl").read_text().splitlines()
CANONICAL = (EXAMPLES / "interactions.jsonl").read_text().splitlines()


@pytest.fixture
def compliance() -> ComplianceRuntime:
    return build_compliance(load_settings(), audit=DatabaseAuditLog(), bus=InProcessEventBus())


async def declare(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID, *keys: str
) -> None:
    declarations = {d.key: d for d in load_declarations(EXAMPLES / "systems.yaml")}
    async with database.transaction() as session:
        for key in keys:
            await compliance.inventory.declare(session, tenant_id, declarations[key])


async def stored(database: Database) -> list[Interaction]:
    async with database.session() as session:
        return list(
            (await session.scalars(select(Interaction).order_by(Interaction.started_at))).all()
        )


async def test_litellm_records_are_imported_without_content(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    await declare(compliance, database, tenant_id, "invoice-data-extraction")
    service = IngestService(compliance.audit)

    async with database.transaction() as session:
        report = await service.ingest(session, tenant_id, LITELLM, LiteLLMSource(BuiltinDetector()))

    rows = await stored(database)
    assert (report.read, report.imported, report.duplicates, report.invalid) == (3, 3, 0, 0)
    assert report.attributed == {"invoice-data-extraction": 1}
    assert report.unattributed == 2
    assert [(r.source, r.status, r.model) for r in rows] == [
        ("litellm", "ok", "gpt-4o"),
        ("litellm", "ok", "gpt-4o"),
        ("litellm", "error", "some-other-model"),
    ]
    assert rows[0].pii_categories == ["email"]
    assert rows[0].source_group == "people-ops"
    assert await text_in_database(database, "hr-suite") == []
    assert (str(rows[0].cost_estimate), rows[0].currency, rows[0].price_version) == (
        "0.000420000",
        "USD",
        "source:litellm",
    )
    assert rows[1].ai_system_id is not None
    for needle in (
        "candidate@example.com",
        "Rank this application",
        "end-user-not-kept",
        "203.0.113.7",
    ):
        assert await text_in_database(database, needle) == []


async def test_importing_the_same_file_again_adds_nothing(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    service = IngestService(compliance.audit)

    async with database.transaction() as session:
        await service.ingest(session, tenant_id, LITELLM, LiteLLMSource())
    async with database.transaction() as session:
        again = await service.ingest(session, tenant_id, LITELLM, LiteLLMSource())

    assert (again.imported, again.duplicates) == (0, 3)
    assert len(await stored(database)) == 3


async def test_the_same_record_id_in_another_tenant_is_not_a_duplicate(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    service = IngestService(compliance.audit)

    async with database.transaction() as session:
        await service.ingest(session, tenant_id, LITELLM, LiteLLMSource())
        other = await service.ingest(session, other_tenant_id, LITELLM, LiteLLMSource())

    assert other.imported == 3


async def test_a_configured_mapping_attributes_records_by_label(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    await declare(compliance, database, tenant_id, "cv-screening", "invoice-data-extraction")
    mappings = [
        IngestMapping(source="litellm", labels={"key_alias": "hr-suite"}, system="cv-screening"),
        IngestMapping(labels={"team_alias": "growth"}, system="not-declared"),
    ]

    async with database.transaction() as session:
        report = await IngestService(compliance.audit, mappings).ingest(
            session, tenant_id, LITELLM, LiteLLMSource()
        )

    assert report.attributed == {"cv-screening": 1, "invoice-data-extraction": 1}
    assert report.unattributed == 1
    assert report.unknown_systems == {"not-declared"}


async def test_canonical_records_name_their_system_directly(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    await declare(compliance, database, tenant_id, "cv-screening")

    async with database.transaction() as session:
        report = await IngestService(compliance.audit).ingest(
            session, tenant_id, CANONICAL, JsonlSource()
        )

    rows = await stored(database)
    assert report.attributed == {"cv-screening": 1}
    assert (rows[0].region, rows[0].input_tokens, rows[0].duration_ms) == ("westeurope", 300, 850)
    assert rows[1].pii_categories == ["email"]


async def test_unreadable_lines_are_skipped_and_reported_by_number_only(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    lines = [LITELLM[0], "{not json", "", '["a list"]', '{"id": "SECRET PROMPT"}', LITELLM[1]]

    async with database.transaction() as session:
        report = await IngestService(compliance.audit).ingest(
            session, tenant_id, lines, LiteLLMSource()
        )

    assert (report.read, report.imported, report.invalid) == (5, 2, 3)
    assert report.invalid_lines == [2, 4, 5]


async def test_strict_stops_at_the_first_unreadable_line_and_imports_nothing(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    async def strict() -> None:
        async with database.transaction() as session:
            await IngestService(compliance.audit).ingest(
                session, tenant_id, [LITELLM[0], "{not json"], LiteLLMSource(), strict=True
            )

    with pytest.raises(IngestError, match="line 2: not valid JSON"):
        await strict()

    assert await stored(database) == []


async def test_an_import_is_audited_with_counts_only(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    async with database.transaction() as session:
        await IngestService(compliance.audit).ingest(session, tenant_id, LITELLM, LiteLLMSource())

    async with database.session() as session:
        entry = (await session.scalars(select(AuditEntry))).one()
    assert (entry.action, entry.outcome, entry.resource_id) == (
        "ingest.completed",
        "imported:3",
        "litellm",
    )
    assert entry.decision == {
        "read": 3,
        "imported": 3,
        "duplicates": 0,
        "invalid": 0,
        "unattributed": 3,
    }


async def test_with_the_usage_meter_as_sink_imported_records_reach_the_roll_ups(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    meter = UsageMeter(load_catalogue())

    async with database.transaction() as session:
        await IngestService(compliance.audit, sink=meter.record).ingest(
            session, tenant_id, LITELLM, LiteLLMSource()
        )

    async with database.session() as session:
        rollup = (
            await session.scalars(select(UsageRollup).where(UsageRollup.scope_type == "tenant"))
        ).one()
    assert (rollup.requests, rollup.failed, rollup.input_tokens) == (3, 1, 360)
    assert str(rollup.cost_estimate) == "0.001260000"


async def test_imported_traffic_feeds_the_scanner(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> None:
    await declare(compliance, database, tenant_id, "invoice-data-extraction")
    now = compliance.clock.now().timestamp()
    recent = {
        **json.loads(LITELLM[1]),
        "startTime": now - 60,
        "endTime": now - 59,
        "model": "model-nobody-declared",
        "model_group": "model-nobody-declared",
    }
    line = json.dumps(recent)

    async with database.transaction() as session:
        await IngestService(compliance.audit).ingest(session, tenant_id, [line], LiteLLMSource())
        await compliance.scanner.run(session, tenant_id)
        findings = await compliance.findings.list(session, tenant_id)

    assert "SCAN-UNDECLARED-MODEL-IN-TRAFFIC" in [finding.rule_id for finding in findings]
