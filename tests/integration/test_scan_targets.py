"""What the scan says of MCP servers, A2A agents and the calls made to them (Phase 5)."""

from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.findings.model import Finding
from ai_arbiter.compliance.inventory.declarations import SystemDeclaration, load_declarations
from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.core.audit import DatabaseAuditLog
from ai_arbiter.core.config import load_settings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.invocation import Invocation
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.targets import GovernedTarget
from tests.integration.test_compliance import EXAMPLES, NOW, FixedClock, declare, scan


class Targets:
    """A directory with whatever the test puts in it."""

    def __init__(self, *targets: GovernedTarget) -> None:
        self.listed = list(targets)

    async def targets(self, session: AsyncSession, tenant_id: UUID) -> Sequence[GovernedTarget]:
        return self.listed


def toolkit(targets: Targets) -> ComplianceRuntime:
    clock = FixedClock()
    return build_compliance(
        load_settings(),
        audit=DatabaseAuditLog(clock),
        bus=InProcessEventBus(),
        clock=clock,
        targets=targets,
    )


@pytest.fixture
def declarations() -> dict[str, SystemDeclaration]:
    return {system.key: system for system in load_declarations(EXAMPLES)}


async def calls(
    database: Database,
    tenant_id: UUID,
    target: str,
    *,
    count: int = 1,
    protocol: str = "mcp",
    known: bool = True,
    outcome: str = "ok",
    reason: str | None = None,
    days_ago: int = 1,
) -> None:
    async with database.transaction() as session:
        for _ in range(count):
            session.add(
                Invocation(
                    id=new_id(),
                    tenant_id=tenant_id,
                    protocol=protocol,
                    target=target,
                    target_known=known,
                    method="tools/call",
                    outcome=outcome,
                    reason=reason,
                    started_at=NOW - timedelta(days=days_ago),
                )
            )


async def findings(database: Database, tenant_id: UUID) -> dict[str, list[str]]:
    """Rule ids of the findings about targets, by what tells them apart."""
    async with database.session() as session:
        rows = (
            await session.scalars(
                select(Finding).where(
                    Finding.tenant_id == tenant_id,
                    Finding.rule_id.not_like("SCAN-SYSTEM%"),
                    Finding.rule_id.not_like("SCAN-CLASSIFICATION%"),
                    Finding.rule_id.not_like("SCAN-HUMAN%"),
                )
            )
        ).all()
        compliance = toolkit(Targets())
        result: dict[str, list[str]] = {}
        for row in rows:
            detail = await compliance.findings.get(session, tenant_id, row.id)
            target = str(detail.evidence[-1].data.get("target"))
            result.setdefault(target, []).append(row.rule_id)
    return {target: sorted(rules) for target, rules in result.items()}


async def test_servers_and_agents_are_reported_for_what_keeps_them_from_being_governed(
    database: Database, tenant_id: UUID, declarations: dict[str, SystemDeclaration]
) -> None:
    compliance = toolkit(Targets())
    await declare(compliance, database, tenant_id, declarations, "cv-screening")
    async with database.session() as session:
        system = await compliance.inventory.get(session, tenant_id, "cv-screening")
    compliance = toolkit(
        Targets(
            GovernedTarget("mcp", "files", system.id, "governable"),
            GovernedTarget("mcp", "old-crm", system.id, "legacy_only"),
            GovernedTarget("mcp", "orphan", None, "governable"),
            GovernedTarget("a2a", "routes", system.id, "governable", "verified"),
            GovernedTarget("a2a", "unsigned-agent", system.id, "governable", "unsigned"),
            GovernedTarget("a2a", "stranger", system.id, "governable", "unknown_key"),
            GovernedTarget("a2a", "forged", system.id, "governable", "invalid"),
            GovernedTarget("a2a", "grpc-agent", system.id, "no_proxied_binding", "verified"),
        )
    )

    stats = await scan(compliance, database, tenant_id)

    assert stats["targets"] == 8
    assert await findings(database, tenant_id) == {
        "mcp:old-crm": ["SCAN-MCP-SERVER-LEGACY-ONLY"],
        "mcp:orphan": ["SCAN-TARGET-WITHOUT-SYSTEM"],
        "a2a:unsigned-agent": ["SCAN-AGENT-CARD-NOT-VERIFIED"],
        "a2a:stranger": ["SCAN-AGENT-CARD-NOT-VERIFIED"],
        "a2a:forged": ["SCAN-AGENT-CARD-INVALID"],
        "a2a:grpc-agent": ["SCAN-AGENT-NOT-GOVERNABLE"],
    }
    async with database.session() as session:
        forged = (
            await session.scalars(
                select(Finding).where(Finding.rule_id == "SCAN-AGENT-CARD-INVALID")
            )
        ).one()
        orphan = (
            await session.scalars(
                select(Finding).where(Finding.rule_id == "SCAN-TARGET-WITHOUT-SYSTEM")
            )
        ).one()
    # A finding about a server or an agent is attached to the system it belongs to.
    assert (forged.severity, forged.ai_system_id) == ("high", system.id)
    assert orphan.ai_system_id is None


async def test_calls_to_what_no_catalogue_holds_and_calls_without_a_grant_are_reported(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    compliance = toolkit(Targets(GovernedTarget("mcp", "files", None, "governable")))
    await calls(database, tenant_id, "files", count=5)
    await calls(
        database, tenant_id, "files", count=3, outcome="denied", reason="MCP-CALL-NOT-GRANTED"
    )
    await calls(database, tenant_id, "files", outcome="denied", reason="MCP-SYSTEM-PROHIBITED")
    await calls(database, tenant_id, "shadow-server", count=2, known=False, outcome="denied")
    await calls(database, tenant_id, "shadow-agent", protocol="a2a", known=False, outcome="denied")
    await calls(database, tenant_id, "long-gone", known=False, outcome="denied", days_ago=45)
    await calls(database, other_tenant_id, "their-shadow", known=False, outcome="denied")

    await scan(compliance, database, tenant_id)
    await scan(compliance, database, tenant_id)

    assert await findings(database, tenant_id) == {
        "mcp:files": ["SCAN-CALLS-NOT-GRANTED", "SCAN-TARGET-WITHOUT-SYSTEM"],
        "mcp:shadow-server": ["SCAN-UNKNOWN-TARGET-IN-TRAFFIC"],
        "a2a:shadow-agent": ["SCAN-UNKNOWN-TARGET-IN-TRAFFIC"],
    }
    async with database.session() as session:
        rows = (await session.scalars(select(Finding))).all()
        compliance_view = toolkit(Targets())
        refused = next(row for row in rows if row.rule_id == "SCAN-CALLS-NOT-GRANTED")
        evidence = (await compliance_view.findings.get(session, tenant_id, refused.id)).evidence
    assert {row.occurrences for row in rows} == {2}
    assert evidence[-1].data["calls_not_granted"] == 3


async def test_a_finding_about_a_target_closes_when_its_cause_is_gone(
    database: Database, tenant_id: UUID
) -> None:
    targets = Targets(GovernedTarget("a2a", "routes", None, "governable", "unsigned"))
    compliance = toolkit(targets)

    await scan(compliance, database, tenant_id)
    targets.listed = [GovernedTarget("a2a", "routes", None, "governable", "verified")]
    await scan(compliance, database, tenant_id)

    async with database.session() as session:
        rows = (await session.scalars(select(Finding))).all()
    assert sorted((row.rule_id, row.status) for row in rows) == [
        ("SCAN-AGENT-CARD-NOT-VERIFIED", "mitigated"),
        ("SCAN-TARGET-WITHOUT-SYSTEM", "open"),
    ]


async def test_without_a_gateway_the_scan_sees_no_targets_and_still_runs(
    database: Database, tenant_id: UUID
) -> None:
    clock = FixedClock()
    compliance = build_compliance(
        load_settings(), audit=DatabaseAuditLog(clock), bus=InProcessEventBus(), clock=clock
    )

    stats = await scan(compliance, database, tenant_id)

    assert (stats["targets"], stats["detections"]) == (0, 0)
