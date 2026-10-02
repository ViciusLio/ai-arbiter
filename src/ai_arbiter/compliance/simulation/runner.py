"""Load a scenario into a tenant and compare what comes out with what it expects."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.inventory.discovery import discover
from ai_arbiter.compliance.runtime import ComplianceRuntime
from ai_arbiter.compliance.scanner.service import TRAFFIC_WINDOW_DAYS
from ai_arbiter.compliance.simulation.model import Scenario
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.interaction import Interaction

# Marks simulated requests everywhere they are stored, so that nobody takes them for
# traffic that happened.
SIMULATION_SOURCE = "simulation"
_ACTIVE = ("open", "confirmed")


@dataclass(frozen=True)
class SystemOutcome:
    key: str
    name: str
    expected_tier: str
    tier: str
    expected_findings: tuple[str, ...]
    findings: tuple[str, ...]

    @property
    def as_expected(self) -> bool:
        return self.tier == self.expected_tier and self.findings == self.expected_findings


@dataclass(frozen=True)
class ScenarioResult:
    scenario: Scenario
    systems: tuple[SystemOutcome, ...]
    expected_candidates: tuple[str, ...]
    candidates: tuple[str, ...]

    @property
    def as_expected(self) -> bool:
        return self.candidates == self.expected_candidates and all(
            system.as_expected for system in self.systems
        )


async def run_scenario(
    session: AsyncSession,
    tenant_id: UUID,
    compliance: ComplianceRuntime,
    scenario: Scenario,
    *,
    reviewer_id: UUID,
) -> ScenarioResult:
    """Declare, classify, review, write the traffic, scan, and compare.

    Safe to repeat: what is already there is left as it is. ``reviewer_id`` is the
    principal recorded as owner of the owned systems and as author of the reviews.
    """
    now = compliance.clock.now()
    systems = {}
    for declaration in scenario.declarations():
        if declaration.key in scenario.owned:
            declaration = declaration.model_copy(update={"owner_principal_id": reviewer_id})
        declared = await compliance.inventory.declare(session, tenant_id, declaration)
        await compliance.classifier.classify_system(session, declared.system)
        systems[declaration.key] = declared.system

    for review in scenario.reviews:
        system = systems[review.system]
        current = await compliance.classifier.current(session, tenant_id, system.id)
        if current is not None and not current.reviewed:
            await compliance.classifier.review(
                session,
                tenant_id,
                system.id,
                decision=review.decision,
                reviewer_id=reviewer_id,
                reason=review.reason,
                tier=review.tier,
            )

    for position, item in enumerate(scenario.traffic):
        prefix = f"{scenario.scenario}:{position}:"
        existing = set(
            await session.scalars(
                select(Interaction.source_record_id).where(
                    Interaction.tenant_id == tenant_id,
                    Interaction.source == SIMULATION_SOURCE,
                    Interaction.source_record_id.startswith(prefix, autoescape=True),
                )
            )
        )
        for number in range(item.requests):
            record_id = f"{prefix}{number}"
            if record_id in existing:
                continue
            session.add(
                Interaction(
                    id=new_id(),
                    tenant_id=tenant_id,
                    ai_system_id=systems[item.system].id if item.system is not None else None,
                    source=SIMULATION_SOURCE,
                    source_record_id=record_id,
                    source_group=item.group,
                    started_at=now - timedelta(days=item.days_ago, minutes=number),
                    status="ok",
                    requested_model=item.model,
                    model=item.model,
                    provider=item.provider,
                    pii_categories=list(item.pii_categories),
                )
            )
    await session.flush()

    await compliance.scanner.run(session, tenant_id)

    outcomes = []
    for key, system in systems.items():
        current = await compliance.classifier.current(session, tenant_id, system.id)
        findings = await compliance.findings.list(
            session, tenant_id, ai_system_id=system.id, statuses=list(_ACTIVE)
        )
        expected = scenario.expected.systems[key]
        outcomes.append(
            SystemOutcome(
                key=key,
                name=system.name,
                expected_tier=expected.tier.value,
                tier=current.tier.value if current is not None else "not_classified",
                expected_findings=tuple(sorted(expected.findings)),
                findings=tuple(sorted(finding.rule_id for finding in findings)),
            )
        )
    wanted = {item.group for item in scenario.traffic if item.group is not None}
    found = await discover(session, tenant_id, now - timedelta(days=TRAFFIC_WINDOW_DAYS))
    candidates = sorted(
        str(item.group)
        for item in found
        if item.source == SIMULATION_SOURCE and item.group in wanted
    )
    return ScenarioResult(
        scenario=scenario,
        systems=tuple(outcomes),
        expected_candidates=tuple(sorted(scenario.expected.candidates)),
        candidates=tuple(candidates),
    )
