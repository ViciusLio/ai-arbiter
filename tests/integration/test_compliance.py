from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select

from ai_arbiter.compliance.classifier.model import Classification, ReviewDecision
from ai_arbiter.compliance.findings.model import (
    Finding,
    FindingStatus,
    SuppressionScope,
)
from ai_arbiter.compliance.inventory.declarations import SystemDeclaration, load_declarations
from ai_arbiter.compliance.inventory.model import Lifecycle
from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.core.audit import AuditEntry, DatabaseAuditLog
from ai_arbiter.core.config import load_settings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.risk import RiskTier
from ai_arbiter.core.errors import ConflictError, NotFoundError
from ai_arbiter.core.events.bus import InProcessEventBus
from ai_arbiter.core.events.model import OutboxEvent
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.database import Database

EXAMPLES = Path(__file__).parents[2] / "examples" / "systems.yaml"
NOW = datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
REVIEWER = new_id()


class FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def compliance(clock: FixedClock) -> ComplianceRuntime:
    return build_compliance(
        load_settings(), audit=DatabaseAuditLog(clock), bus=InProcessEventBus(), clock=clock
    )


@pytest.fixture
def declarations() -> dict[str, SystemDeclaration]:
    return {system.key: system for system in load_declarations(EXAMPLES)}


async def declare(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
    *keys: str,
    classify: bool = True,
) -> None:
    async with database.transaction() as session:
        for key in keys or declarations:
            declared = await compliance.inventory.declare(session, tenant_id, declarations[key])
            if classify:
                await compliance.classifier.classify_system(session, declared.system)


async def audit_actions(database: Database) -> list[tuple[str, str]]:
    async with database.session() as session:
        entries = (await session.scalars(select(AuditEntry).order_by(AuditEntry.seq))).all()
    return [(entry.action, entry.outcome) for entry in entries]


async def open_findings(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> dict[str, list[str]]:
    """Rule ids of active findings, by system key."""
    async with database.session() as session:
        systems = {s.id: s.key for s in await compliance.inventory.list(session, tenant_id)}
        findings = await compliance.findings.list(
            session, tenant_id, statuses=["open", "confirmed"]
        )
    result: dict[str, list[str]] = {}
    for finding in findings:
        key = systems.get(finding.ai_system_id, "(tenant)") if finding.ai_system_id else "(tenant)"
        result.setdefault(key, []).append(finding.rule_id)
    return {key: sorted(rules) for key, rules in result.items()}


async def scan(
    compliance: ComplianceRuntime, database: Database, tenant_id: UUID
) -> dict[str, Any]:
    async with database.transaction() as session:
        return dict((await compliance.scanner.run(session, tenant_id)).stats)


# --- inventory ---------------------------------------------------------------------------


async def test_a_declaration_creates_the_system_with_its_roles_and_facts(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    async with database.transaction() as session:
        declared = await compliance.inventory.declare(
            session, tenant_id, declarations["cv-screening"], actor_id=REVIEWER
        )

    assert declared.change == "created"
    assert (declared.system.key, declared.system.origin) == ("cv-screening", "declared")
    assert [role.role for role in declared.roles] == ["deployer"]
    assert declared.system.attributes["annex3.employment_recruitment"] is True
    assert declared.system.models_used[0]["model"] == "vendor-ranker-2"
    assert await audit_actions(database) == [("system.declared", "ok")]
    async with database.session() as session:
        events = (await session.scalars(select(OutboxEvent))).all()
    assert [event.type for event in events] == ["system.declared"]
    assert events[0].payload["ai_system_id"] == str(declared.system.id)


async def test_declaring_again_changes_nothing_and_a_real_change_is_recorded(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    original = declarations["cv-screening"]
    changed = original.model_copy(update={"name": "CV screening v2"})

    async with database.transaction() as session:
        first = await compliance.inventory.declare(session, tenant_id, original)
        again = await compliance.inventory.declare(session, tenant_id, original)
        updated = await compliance.inventory.declare(session, tenant_id, changed)

    assert (first.change, again.change, updated.change) == ("created", "unchanged", "changed")
    assert updated.system.id == first.system.id
    assert updated.system.name == "CV screening v2"
    assert [action for action, _ in await audit_actions(database)] == [
        "system.declared",
        "system.changed",
    ]


async def test_a_misspelt_fact_or_a_wrong_type_is_refused(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    base = declarations["cv-screening"]
    misspelt = base.model_copy(update={"facts": {**base.facts, "annex3.employement": True}})
    wrong_type = base.model_copy(update={"facts": {**base.facts, "annex3.employment": "yes"}})

    async with database.transaction() as session:
        with pytest.raises(ConflictError, match=r"unknown facts: annex3\.employement"):
            await compliance.inventory.declare(session, tenant_id, misspelt)
        with pytest.raises(ConflictError, match=r"'annex3\.employment' must be a boolean"):
            await compliance.inventory.declare(session, tenant_id, wrong_type)


async def test_systems_belong_to_their_tenant(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    other_tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")

    async with database.transaction() as session:
        assert await compliance.inventory.list(session, other_tenant_id) == []
        with pytest.raises(NotFoundError):
            await compliance.inventory.get(session, other_tenant_id, "cv-screening")
        same_key = await compliance.inventory.declare(
            session, other_tenant_id, declarations["cv-screening"]
        )
        mine = await compliance.inventory.get(session, tenant_id, "cv-screening")

    assert same_key.change == "created"
    assert same_key.system.id != mine.id


# --- classification and review -----------------------------------------------------------


async def test_the_example_systems_get_the_expected_indicative_tiers(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations)

    tiers = {}
    async with database.session() as session:
        for system in await compliance.inventory.list(session, tenant_id):
            current = await compliance.classifier.current(session, tenant_id, system.id)
            assert current is not None
            tiers[system.key] = (current.tier.value, current.status)

    assert tiers == {
        "call-centre-mood-monitor": ("prohibited", "proposed"),
        "customer-support-assistant": ("transparency", "proposed"),
        "cv-screening": ("high_risk", "proposed"),
        "demand-forecast-prototype": ("out_of_scope", "proposed"),
        "invoice-data-extraction": ("minimal", "proposed"),
        "loan-pre-screening": ("minimal", "proposed"),
        "marketing-copy-generator": ("undetermined", "proposed"),
    }


async def test_a_classification_is_stored_with_its_trace_and_audited_as_a_decision(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")

    async with database.session() as session:
        stored = (await session.scalars(select(Classification))).one()
        entry = (
            await session.scalars(
                select(AuditEntry).where(AuditEntry.action == "system.classified")
            )
        ).one()

    assert (stored.rulepack, stored.tier) == ("ai-act", "high_risk")
    assert stored.regulation_as_of is not None
    assert stored.missing_facts == []
    assert [item["rule_id"] for item in stored.trace] == [
        "AIA-ART4-AI-LITERACY",
        "AIA-ANNEX3-4A-RECRUITMENT",
    ]
    assert stored.obligations[1]["legal_refs"] == ["6(2)", "Annex III(4)(a)"]
    assert entry.outcome == "tier:high_risk"
    assert entry.decision is not None
    assert entry.decision["kind"] == "classification"
    assert entry.decision["details"]["pack_review"] == "pending"


async def test_an_unchanged_system_is_not_classified_again_and_a_change_supersedes(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    base = declarations["marketing-copy-generator"]
    await declare(compliance, database, tenant_id, declarations, base.key)
    completed = base.model_copy(
        update={
            "facts": {**declarations["invoice-data-extraction"].facts},
        }
    )

    async with database.transaction() as session:
        system = await compliance.inventory.get(session, tenant_id, base.key)
        first = await compliance.classifier.current(session, tenant_id, system.id)
        _, created_again = await compliance.classifier.classify_system(session, system)
        declared = await compliance.inventory.declare(session, tenant_id, completed)
        second, created = await compliance.classifier.classify_system(session, declared.system)
        history = await compliance.classifier.history(session, tenant_id, system.id)

    assert first is not None
    assert created_again is False
    assert created is True
    assert (first.tier, second.tier) == (RiskTier.UNDETERMINED, RiskTier.MINIMAL)
    assert [item.superseded_by for item in history] == [second.classification.id, None]


async def test_questions_are_listed_in_questionnaire_order(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "marketing-copy-generator")

    async with database.session() as session:
        system = await compliance.inventory.get(session, tenant_id, "marketing-copy-generator")
        current = await compliance.classifier.current(session, tenant_id, system.id)

    assert current is not None
    questions = current.classification.missing_facts
    assert questions[0] == "prohibited.manipulative_techniques"
    stages = [compliance.ai_act_pack.facts[name].stage for name in questions]
    order = list(compliance.ai_act_pack.stages)
    assert [order.index(stage) for stage in stages if stage] == sorted(
        order.index(stage) for stage in stages if stage
    )


async def review(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    key: str,
    decision: ReviewDecision,
    **values: Any,
) -> Any:
    async with database.transaction() as session:
        system = await compliance.inventory.get(session, tenant_id, key)
        return await compliance.classifier.review(
            session, tenant_id, system.id, decision=decision, reviewer_id=REVIEWER, **values
        )


async def test_a_classification_is_a_proposal_until_a_person_confirms_it(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")
    async with database.session() as session:
        system = await compliance.inventory.get(session, tenant_id, "cv-screening")
        before = await compliance.directory.resolve(session, tenant_id, system.id)

    confirmed = await review(
        compliance, database, tenant_id, "cv-screening", ReviewDecision.CONFIRMED
    )

    async with database.session() as session:
        after = await compliance.directory.resolve(session, tenant_id, system.id)
    assert (before.tier, before.reviewed) == (RiskTier.HIGH_RISK, False)
    assert (confirmed.status, confirmed.tier) == ("confirmed", RiskTier.HIGH_RISK)
    assert (after.tier, after.reviewed) == (RiskTier.HIGH_RISK, True)
    assert after.classification_id == confirmed.classification.id
    assert (await audit_actions(database))[-1] == ("classification.confirmed", "tier:high_risk")
    async with database.session() as session:
        entry = (await session.scalars(select(AuditEntry).order_by(AuditEntry.seq.desc()))).first()
    assert entry is not None
    assert entry.actor_id == REVIEWER


async def test_an_override_needs_a_reason_and_keeps_the_engine_result(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "loan-pre-screening")

    with pytest.raises(ConflictError, match="reason of at least 10"):
        await review(
            compliance,
            database,
            tenant_id,
            "loan-pre-screening",
            ReviewDecision.OVERRIDDEN,
            tier=RiskTier.HIGH_RISK,
            reason="no",
        )
    with pytest.raises(ConflictError, match="needs the tier"):
        await review(
            compliance,
            database,
            tenant_id,
            "loan-pre-screening",
            ReviewDecision.OVERRIDDEN,
            reason="The derogation does not hold.",
        )
    overridden = await review(
        compliance,
        database,
        tenant_id,
        "loan-pre-screening",
        ReviewDecision.OVERRIDDEN,
        tier=RiskTier.HIGH_RISK,
        reason="The provider's assessment does not cover our use.",
    )

    assert overridden.classification.tier == "minimal"
    assert (overridden.tier, overridden.status) == (RiskTier.HIGH_RISK, "overridden")
    assert overridden.review is not None
    assert overridden.review.reviewer_id == REVIEWER


async def test_an_undetermined_classification_cannot_be_confirmed(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "marketing-copy-generator")

    with pytest.raises(ConflictError, match="cannot be confirmed"):
        await review(
            compliance, database, tenant_id, "marketing-copy-generator", ReviewDecision.CONFIRMED
        )
    with pytest.raises(ConflictError, match="override instead"):
        await review(
            compliance,
            database,
            tenant_id,
            "marketing-copy-generator",
            ReviewDecision.CONFIRMED,
            tier=RiskTier.MINIMAL,
        )


async def test_a_new_classification_needs_its_own_review(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")
    await review(compliance, database, tenant_id, "cv-screening", ReviewDecision.CONFIRMED)
    base = declarations["cv-screening"]
    changed = base.model_copy(update={"facts": {**base.facts, "transparency.deep_fake": True}})

    async with database.transaction() as session:
        declared = await compliance.inventory.declare(session, tenant_id, changed)
        current, created = await compliance.classifier.classify_system(session, declared.system)

    assert created
    assert (current.status, current.reviewed) == ("proposed", False)


async def test_a_system_without_classification_resolves_to_undetermined(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening", classify=False)

    async with database.session() as session:
        system = await compliance.inventory.get(session, tenant_id, "cv-screening")
        profiles = [
            await compliance.directory.resolve(session, tenant_id, system.id),
            await compliance.directory.resolve(session, tenant_id, None),
            await compliance.directory.resolve(session, tenant_id, new_id()),
        ]
        with pytest.raises(NotFoundError):
            await compliance.classifier.review(
                session,
                tenant_id,
                system.id,
                decision=ReviewDecision.CONFIRMED,
                reviewer_id=REVIEWER,
            )

    assert [profile.tier for profile in profiles] == [RiskTier.UNDETERMINED] * 3


# --- scanner and findings ----------------------------------------------------------------


async def test_a_scan_of_the_examples_reports_what_each_system_is_missing(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations)

    stats = await scan(compliance, database, tenant_id)

    assert stats["systems"] == 7
    assert stats["opened"] == stats["detections"]
    no_owner, unreviewed = "SCAN-SYSTEM-WITHOUT-OWNER", "SCAN-CLASSIFICATION-NOT-REVIEWED"
    assert await open_findings(compliance, database, tenant_id) == {
        "call-centre-mood-monitor": sorted([no_owner, unreviewed, "SCAN-PROHIBITED-PRACTICE"]),
        "customer-support-assistant": sorted([no_owner, unreviewed]),
        "cv-screening": sorted([no_owner, unreviewed, "SCAN-HUMAN-OVERSIGHT-NOT-ATTESTED"]),
        "demand-forecast-prototype": sorted([no_owner, unreviewed, "SCAN-ROLE-NOT-COVERED"]),
        "invoice-data-extraction": sorted([no_owner, unreviewed]),
        "loan-pre-screening": sorted([no_owner, unreviewed, "SCAN-DEROGATION-WITHOUT-ASSESSMENT"]),
        "marketing-copy-generator": sorted([no_owner, "SCAN-CLASSIFICATION-UNDETERMINED"]),
    }


async def test_a_finding_about_a_future_obligation_is_about_readiness(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    clock: FixedClock,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "cv-screening")

    await scan(compliance, database, tenant_id)
    async with database.session() as session:
        before = (
            await session.scalars(
                select(Finding).where(Finding.rule_id == "SCAN-HUMAN-OVERSIGHT-NOT-ATTESTED")
            )
        ).one()
        severity_before = before.severity
    clock.current = datetime(2027, 12, 2, 9, 0, tzinfo=UTC)
    await scan(compliance, database, tenant_id)
    async with database.session() as session:
        after = await session.get_one(Finding, before.id)

    assert severity_before == "low"
    assert after.severity == "high"
    assert str(after.applies_from) == "2027-12-02"
    assert after.legal_refs == [{"regulation": "EU-AI-ACT", "article": "26(2)"}]
    assert after.occurrences == 2


async def test_a_repeated_detection_updates_the_finding_instead_of_adding_one(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    clock: FixedClock,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "invoice-data-extraction")

    first = await scan(compliance, database, tenant_id)
    clock.current += timedelta(days=1)
    second = await scan(compliance, database, tenant_id)

    async with database.session() as session:
        findings = (await session.scalars(select(Finding))).all()
        detail = await compliance.findings.get(session, tenant_id, findings[0].id)
    assert (first["opened"], second.get("opened", 0), second["refreshed"]) == (2, 0, 2)
    assert len(findings) == 2
    assert all(finding.occurrences == 2 for finding in findings)
    assert all(finding.last_seen > finding.first_seen for finding in findings)
    assert len(detail.evidence) == 1
    assert detail.evidence[0].data["system_key"] == "invoice-data-extraction"


async def test_fixing_the_cause_closes_the_finding_at_the_next_scan(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "invoice-data-extraction")
    await scan(compliance, database, tenant_id)

    await review(
        compliance, database, tenant_id, "invoice-data-extraction", ReviewDecision.CONFIRMED
    )
    stats = await scan(compliance, database, tenant_id)

    assert stats["mitigated"] == 1
    assert await open_findings(compliance, database, tenant_id) == {
        "invoice-data-extraction": ["SCAN-SYSTEM-WITHOUT-OWNER"]
    }
    async with database.session() as session:
        closed = (await session.scalars(select(Finding).where(Finding.status == "mitigated"))).one()
        detail = await compliance.findings.get(session, tenant_id, closed.id)
    assert [(r.from_status, r.to_status, r.reviewer_id, r.reason) for r in detail.reviews] == [
        ("open", "mitigated", None, "no longer detected")
    ]


async def interactions(
    database: Database,
    tenant_id: UUID,
    system_id: UUID | None,
    *,
    count: int = 1,
    model: str = "gpt-4o",
    pii: Sequence[str] = (),
    at: datetime = NOW - timedelta(days=1),
) -> None:
    async with database.transaction() as session:
        for _ in range(count):
            identifier = new_id()
            session.add(
                Interaction(
                    id=identifier,
                    tenant_id=tenant_id,
                    ai_system_id=system_id,
                    source_record_id=str(identifier),
                    started_at=at,
                    status="ok",
                    requested_model=model,
                    model=model,
                    pii_categories=list(pii),
                )
            )


async def test_traffic_that_contradicts_the_declaration_is_reported(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "invoice-data-extraction")
    async with database.session() as session:
        system = await compliance.inventory.get(session, tenant_id, "invoice-data-extraction")
    await interactions(database, tenant_id, system.id, count=3)
    await interactions(database, tenant_id, system.id, model="shadow-model", pii=["email", "iban"])
    await interactions(database, tenant_id, system.id, model="old", at=NOW - timedelta(days=45))
    await interactions(database, tenant_id, None, count=2)

    await scan(compliance, database, tenant_id)

    found = await open_findings(compliance, database, tenant_id)
    assert "SCAN-UNDECLARED-MODEL-IN-TRAFFIC" in found["invoice-data-extraction"]
    assert "SCAN-PERSONAL-DATA-NOT-DECLARED" in found["invoice-data-extraction"]
    assert found["(tenant)"] == ["SCAN-UNATTRIBUTED-TRAFFIC"]
    async with database.session() as session:
        finding = (
            await session.scalars(
                select(Finding).where(Finding.rule_id == "SCAN-UNDECLARED-MODEL-IN-TRAFFIC")
            )
        ).one()
        evidence = (await compliance.findings.get(session, tenant_id, finding.id)).evidence[0].data
    assert evidence["undeclared_models"] == ["shadow-model"]
    assert evidence["requests"] == 4
    assert evidence["pii_categories"] == ["email", "iban"]


async def test_a_retired_system_that_still_sends_traffic_is_reported(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    retired = declarations["invoice-data-extraction"].model_copy(
        update={"lifecycle": Lifecycle.RETIRED}
    )
    async with database.transaction() as session:
        declared = await compliance.inventory.declare(session, tenant_id, retired)
        await compliance.classifier.classify_system(session, declared.system)
    await interactions(database, tenant_id, declared.system.id)

    await scan(compliance, database, tenant_id)

    found = await open_findings(compliance, database, tenant_id)
    assert "SCAN-RETIRED-SYSTEM-IN-USE" in found["invoice-data-extraction"]


async def one_finding(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
    rule: str = "SCAN-SYSTEM-WITHOUT-OWNER",
) -> UUID:
    await declare(compliance, database, tenant_id, declarations, "invoice-data-extraction")
    await scan(compliance, database, tenant_id)
    async with database.session() as session:
        return (await session.scalars(select(Finding.id).where(Finding.rule_id == rule))).one()


async def move(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    finding_id: UUID,
    to: FindingStatus,
    **values: Any,
) -> Finding:
    async with database.transaction() as session:
        return await compliance.findings.transition(
            session, tenant_id, finding_id, to, reviewer_id=REVIEWER, **values
        )


async def test_a_reviewer_confirms_a_finding_and_later_declares_it_fixed(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    finding_id = await one_finding(compliance, database, tenant_id, declarations)

    confirmed = await move(compliance, database, tenant_id, finding_id, FindingStatus.CONFIRMED)
    mitigated = await move(compliance, database, tenant_id, finding_id, FindingStatus.MITIGATED)
    stats = await scan(compliance, database, tenant_id)

    assert (confirmed.status, mitigated.status) == ("confirmed", "mitigated")
    assert stats["reopened"] == 1
    async with database.session() as session:
        detail = await compliance.findings.get(session, tenant_id, finding_id)
    assert detail.finding.status == "open"
    assert [(r.to_status, r.reviewer_id, r.reason) for r in detail.reviews] == [
        ("confirmed", REVIEWER, ""),
        ("mitigated", REVIEWER, ""),
        ("open", None, "detected again"),
    ]
    actions = [action for action, _ in await audit_actions(database)]
    assert actions[-4:] == [
        "finding.confirmed",
        "finding.mitigated",
        "finding.open",
        "scan.completed",
    ]


async def test_moves_the_lifecycle_does_not_allow_are_refused(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    finding_id = await one_finding(compliance, database, tenant_id, declarations)

    with pytest.raises(ConflictError, match="open cannot become mitigated"):
        await move(compliance, database, tenant_id, finding_id, FindingStatus.MITIGATED)
    with pytest.raises(ConflictError, match="needs a reason"):
        await move(compliance, database, tenant_id, finding_id, FindingStatus.FALSE_POSITIVE)
    with pytest.raises(ConflictError, match="expiry date in the future"):
        await move(
            compliance,
            database,
            tenant_id,
            finding_id,
            FindingStatus.ACCEPTED,
            reason="Accepted by the steering committee.",
        )
    with pytest.raises(ConflictError, match="only be created with a false positive"):
        await move(
            compliance,
            database,
            tenant_id,
            finding_id,
            FindingStatus.CONFIRMED,
            suppress=SuppressionScope.RULE,
        )
    with pytest.raises(NotFoundError):
        await move(compliance, database, tenant_id, new_id(), FindingStatus.CONFIRMED)


async def test_an_accepted_risk_comes_back_when_the_acceptance_expires(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    clock: FixedClock,
    declarations: dict[str, SystemDeclaration],
) -> None:
    finding_id = await one_finding(compliance, database, tenant_id, declarations)
    await move(
        compliance,
        database,
        tenant_id,
        finding_id,
        FindingStatus.ACCEPTED,
        reason="An owner will be named next quarter.",
        accepted_until=(NOW + timedelta(days=30)).date(),
    )

    during = await scan(compliance, database, tenant_id)
    clock.current = NOW + timedelta(days=31)
    after = await scan(compliance, database, tenant_id)

    assert during["unchanged"] == 1
    assert after["reopened"] == 1
    async with database.session() as session:
        finding = await session.get_one(Finding, finding_id)
    assert (finding.status, finding.accepted_until) == ("open", None)


async def test_a_false_positive_with_a_suppression_stops_the_rule_for_that_system(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    finding_id = await one_finding(compliance, database, tenant_id, declarations)
    await declare(compliance, database, tenant_id, declarations, "cv-screening")

    await move(
        compliance,
        database,
        tenant_id,
        finding_id,
        FindingStatus.FALSE_POSITIVE,
        reason="Ownership is tracked in the CMDB.",
        suppress=SuppressionScope.SYSTEM,
    )
    stats = await scan(compliance, database, tenant_id)

    found = await open_findings(compliance, database, tenant_id)
    assert stats["suppressed"] == 1
    assert "SCAN-SYSTEM-WITHOUT-OWNER" not in found["invoice-data-extraction"]
    assert "SCAN-SYSTEM-WITHOUT-OWNER" in found["cv-screening"]
    async with database.transaction() as session:
        suppressions = await compliance.findings.suppressions(session, tenant_id)
        feedback = await compliance.findings.rule_feedback(session, tenant_id)
        await compliance.findings.remove_suppression(
            session, tenant_id, suppressions[0].id, actor_id=REVIEWER
        )
        with pytest.raises(NotFoundError):
            await compliance.findings.remove_suppression(
                session, tenant_id, suppressions[0].id, actor_id=REVIEWER
            )
    assert (suppressions[0].scope_type, suppressions[0].created_by) == ("system", REVIEWER)
    assert feedback["SCAN-SYSTEM-WITHOUT-OWNER"] == {"false_positive": 1, "open": 1}


async def test_a_suppression_can_cover_a_whole_rule_and_can_expire(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    clock: FixedClock,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations, "invoice-data-extraction")
    async with database.transaction() as session:
        await compliance.findings.suppress(
            session,
            tenant_id,
            rule_id="SCAN-SYSTEM-WITHOUT-OWNER",
            scope=SuppressionScope.RULE,
            reason="Owners are being collected this month.",
            created_by=REVIEWER,
            expires_at=NOW + timedelta(days=10),
        )
        with pytest.raises(ConflictError, match="needs a reason"):
            await compliance.findings.suppress(
                session,
                tenant_id,
                rule_id="X",
                scope=SuppressionScope.RULE,
                reason="short",
                created_by=None,
            )
        with pytest.raises(ConflictError, match="needs its reference"):
            await compliance.findings.suppress(
                session,
                tenant_id,
                rule_id="X",
                scope=SuppressionScope.SYSTEM,
                reason="A long enough reason.",
                created_by=None,
            )

    during = await scan(compliance, database, tenant_id)
    clock.current = NOW + timedelta(days=11)
    after = await scan(compliance, database, tenant_id)

    assert during["suppressed"] == 1
    assert after.get("suppressed", 0) == 0
    assert (
        "SCAN-SYSTEM-WITHOUT-OWNER"
        in (await open_findings(compliance, database, tenant_id))["invoice-data-extraction"]
    )


async def test_findings_of_one_tenant_are_invisible_to_another(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    other_tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    finding_id = await one_finding(compliance, database, tenant_id, declarations)

    async with database.transaction() as session:
        assert await compliance.findings.list(session, other_tenant_id) == []
        with pytest.raises(NotFoundError):
            await compliance.findings.get(session, other_tenant_id, finding_id)
        with pytest.raises(NotFoundError):
            await compliance.findings.transition(
                session, other_tenant_id, finding_id, FindingStatus.CONFIRMED, reviewer_id=REVIEWER
            )
    assert (await scan(compliance, database, other_tenant_id))["systems"] == 0


async def test_the_audit_chain_holds_after_compliance_activity(
    compliance: ComplianceRuntime,
    database: Database,
    tenant_id: UUID,
    declarations: dict[str, SystemDeclaration],
) -> None:
    await declare(compliance, database, tenant_id, declarations)
    await scan(compliance, database, tenant_id)

    async with database.session() as session:
        report = await DatabaseAuditLog().verify(session, tenant_id)
        names = [s.name for s in await compliance.inventory.list(session, tenant_id)]
        entries = (await session.scalars(select(AuditEntry))).all()

    assert report.ok
    assert report.entries == len(entries) > 30
    assert not any(name in str(entry.decision) for entry in entries for name in names)
