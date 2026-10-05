"""Collect observations about each system and report what the scan rules match."""

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.classifier.engine import COVERED_ROLES
from ai_arbiter.compliance.classifier.service import ClassifierService
from ai_arbiter.compliance.findings.model import ScanRun
from ai_arbiter.compliance.findings.service import Evidence, FindingCandidate, FindingService
from ai_arbiter.compliance.inventory.discovery import discover, ungrouped_requests
from ai_arbiter.compliance.inventory.model import AISystem, AISystemRole
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.domain.risk import ActorRole
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.interaction import PII_CATEGORIES_AS_TEXT, Interaction, read_categories
from ai_arbiter.core.invocation import Invocation
from ai_arbiter.core.ports import AuditLog, NoTargetDirectory, TargetDirectory
from ai_arbiter.core.rules import Facts, FactType, RuleKind, RuleMatch, RulePack, evaluate

TRAFFIC_WINDOW_DAYS = 30
CANDIDATE_FACT = "candidate.requests_30d"
TARGET_FACT = "target.protocol"
# The rules of the proxies that deny a call for want of a grant.
NOT_GRANTED_RULES = ("MCP-CALL-NOT-GRANTED", "A2A-CALL-NOT-GRANTED")
# Declared facts the scan rules read as they are from the declaration.
_DECLARED_PREFIXES = ("controls.", "data.")


def severity_on(match: RuleMatch, today: date) -> str:
    """Severity of a match today: lower while the obligation does not apply yet."""
    not_yet = match.applies_from is not None and match.applies_from > today
    return (match.severity_before if not_yet and match.severity_before else match.severity) or "low"


class ScannerService:
    def __init__(
        self,
        pack: RulePack,
        classifier: ClassifierService,
        findings: FindingService,
        audit: AuditLog,
        clock: Clock | None = None,
        targets: TargetDirectory | None = None,
    ) -> None:
        self.pack = pack
        self._targets: TargetDirectory = targets if targets is not None else NoTargetDirectory()
        self._classifier = classifier
        self._findings = findings
        self._audit = audit
        self._clock = clock if clock is not None else SystemClock()

    def declared_facts(self) -> Mapping[str, FactType]:
        """The facts of the scan pack that a declaration answers."""
        return {
            name: spec.type
            for name, spec in self.pack.facts.items()
            if name.startswith(_DECLARED_PREFIXES)
        }

    async def _traffic(
        self, session: AsyncSession, system: AISystem, since: datetime
    ) -> dict[str, Any]:
        # The system's own keys, and keys of the project it names that are tied to no
        # system: declaring the project is enough for its traffic to count (ADR-0042).
        own = Interaction.ai_system_id == system.id
        if system.project_id is not None:
            own = or_(
                own,
                and_(
                    Interaction.ai_system_id.is_(None),
                    Interaction.project_id == system.project_id,
                ),
            )
        base = (
            Interaction.tenant_id == system.tenant_id,
            own,
            Interaction.started_at >= since,
        )
        requests = int(await session.scalar(select(func.count()).where(*base)) or 0)
        models = await session.execute(
            select(Interaction.model, Interaction.requested_model).where(*base).distinct()
        )
        declared = {
            str(item.get("model")) for item in system.models_used or [] if isinstance(item, Mapping)
        }
        undeclared = sorted(
            {
                str(model or requested)
                for model, requested in models
                if (model or requested) and not {model, requested} & declared
            }
        )
        categories: set[str] = set()
        # Every distinct combination, not a sample of rows: a few values, whatever the traffic.
        for value in await session.scalars(select(PII_CATEGORIES_AS_TEXT).where(*base).distinct()):
            categories.update(read_categories(value))
        return {
            "requests": requests,
            "undeclared_models": undeclared,
            "pii_categories": sorted(categories),
        }

    async def observe(
        self, session: AsyncSession, system: AISystem
    ) -> tuple[Facts, dict[str, Any]]:
        """Facts about a system for the scan rules, and the details kept as evidence."""
        since = self._clock.now() - timedelta(days=TRAFFIC_WINDOW_DAYS)
        current = await self._classifier.current(session, system.tenant_id, system.id)
        roles = frozenset(
            ActorRole(role)
            for role in await session.scalars(
                select(AISystemRole.role).where(AISystemRole.ai_system_id == system.id)
            )
        )
        traffic = await self._traffic(session, system, since)
        attributes = system.attributes or {}
        obligations = current.classification.obligations if current else []
        facts: dict[str, Any] = {
            "system.lifecycle": system.lifecycle,
            "system.has_owner": system.owner_principal_id is not None,
            "roles.not_covered": bool(roles - COVERED_ROLES),
            "classification.exists": current is not None,
            "classification.tier": current.tier.value if current else None,
            "classification.reviewed": current.reviewed if current else None,
            "classification.derogation_claimed": attributes.get("high_risk.derogation_claimed")
            is True,
            "classification.derogation_evidence": bool(
                attributes.get("high_risk.derogation_assessment_ref")
            ),
            "obligations.transparency_as_deployer": any(
                str(item.get("id", "")).startswith("AIA-ART50")
                and item.get("applies_to_declared_roles")
                and "deployer" in (item.get("roles") or [])
                for item in obligations
                if isinstance(item, Mapping)
            ),
            "traffic.requests_30d": traffic["requests"],
            "traffic.undeclared_model_count": len(traffic["undeclared_models"]),
            "traffic.pii_detected": bool(traffic["pii_categories"]),
        }
        for name in self.declared_facts():
            if attributes.get(name) is not None:
                facts[name] = attributes[name]
        details = {
            "system_key": system.key,
            "classification_id": str(current.classification.id) if current else None,
            "window_days": TRAFFIC_WINDOW_DAYS,
            **traffic,
        }
        return facts, details

    def _candidates(
        self,
        facts: Facts,
        details: Mapping[str, Any],
        system_id: UUID | None,
        today: date,
        distinguishing: str = "",
    ) -> list[FindingCandidate]:
        candidates = []
        for match in evaluate(self.pack, RuleKind.FINDING, facts):
            observed = {
                trace.fact: facts.get(trace.fact) for trace in match.matched if trace.fact in facts
            }
            candidates.append(
                FindingCandidate(
                    rule_id=match.rule_id,
                    rulepack_version=match.pack_version,
                    severity=severity_on(match, today),
                    message_key=match.message_key,
                    ai_system_id=system_id,
                    distinguishing=distinguishing,
                    legal_refs=[
                        {"regulation": ref.regulation, "article": ref.article}
                        for ref in match.legal_refs
                    ],
                    applies_from=match.applies_from,
                    evidence=[Evidence(kind="observation", data={"facts": observed, **details})],
                )
            )
        return candidates

    async def _scan_targets(
        self, session: AsyncSession, tenant_id: UUID, since: datetime, now: datetime
    ) -> tuple[int, list[FindingCandidate]]:
        """The MCP servers and A2A agents of the catalogues, and the calls made to them.

        A finding about a server or an agent is attached to the AI system it belongs to,
        when it belongs to one.
        """
        in_window = (Invocation.tenant_id == tenant_id, Invocation.started_at >= since)
        refused: dict[tuple[str, str], int] = {
            (str(protocol), str(target)): int(count)
            for protocol, target, count in await session.execute(
                select(Invocation.protocol, Invocation.target, func.count())
                .where(
                    *in_window,
                    Invocation.target_known.is_(True),
                    Invocation.reason.in_(NOT_GRANTED_RULES),
                )
                .group_by(Invocation.protocol, Invocation.target)
            )
        }
        candidates: list[FindingCandidate] = []
        targets = await self._targets.targets(session, tenant_id)
        for target in targets:
            reference = f"{target.protocol}:{target.key}"
            not_granted = refused.get((target.protocol, target.key), 0)
            candidates += self._candidates(
                {
                    TARGET_FACT: target.protocol,
                    "target.governability": target.governability,
                    "target.verification": target.verification,
                    "target.has_system": target.ai_system_id is not None,
                    "target.calls_not_granted_30d": not_granted,
                },
                {
                    "target": reference,
                    "window_days": TRAFFIC_WINDOW_DAYS,
                    "calls_not_granted": not_granted,
                },
                target.ai_system_id,
                now.date(),
                distinguishing=reference,
            )
        unknown = await session.execute(
            select(Invocation.protocol, Invocation.target, func.count())
            .where(*in_window, Invocation.target_known.is_(False))
            .group_by(Invocation.protocol, Invocation.target)
            .order_by(Invocation.protocol, Invocation.target)
        )
        for protocol, name, count in unknown:
            reference = f"{protocol}:{name}"
            candidates += self._candidates(
                {"unknown_target.calls_30d": int(count)},
                {"target": reference, "window_days": TRAFFIC_WINDOW_DAYS, "calls": int(count)},
                None,
                now.date(),
                distinguishing=reference,
            )
        return len(targets), candidates

    async def run(
        self, session: AsyncSession, tenant_id: UUID, *, actor_id: UUID | None = None
    ) -> ScanRun:
        """Scan every declared system of a tenant and the tenant's unattributed traffic."""
        now = self._clock.now()
        scan = ScanRun(
            tenant_id=tenant_id, rulepack_version=self.pack.version, started_at=now, stats={}
        )
        session.add(scan)
        await session.flush()
        systems: Sequence[AISystem] = (
            await session.scalars(
                select(AISystem).where(AISystem.tenant_id == tenant_id).order_by(AISystem.key)
            )
        ).all()
        candidates: list[FindingCandidate] = []
        for system in systems:
            facts, details = await self.observe(session, system)
            candidates += self._candidates(facts, details, system.id, now.date())

        since = now - timedelta(days=TRAFFIC_WINDOW_DAYS)
        if CANDIDATE_FACT in self.pack.facts:
            # One finding per candidate system; what nothing groups stays one finding.
            discovered = await discover(session, tenant_id, since)
            for found in discovered:
                candidates += self._candidates(
                    {CANDIDATE_FACT: found.requests},
                    {"window_days": TRAFFIC_WINDOW_DAYS, **found.details()},
                    None,
                    now.date(),
                    distinguishing=found.reference,
                )
            unattributed = await ungrouped_requests(session, tenant_id, since)
        else:
            # A scan pack from before discovery: every such request in one finding.
            discovered = []
            unattributed = int(
                await session.scalar(
                    select(func.count()).where(
                        Interaction.tenant_id == tenant_id,
                        Interaction.ai_system_id.is_(None),
                        Interaction.started_at >= since,
                    )
                )
                or 0
            )
        candidates += self._candidates(
            {"traffic.unattributed_requests_30d": unattributed},
            {"window_days": TRAFFIC_WINDOW_DAYS, "requests": unattributed},
            None,
            now.date(),
        )

        governed = 0
        if TARGET_FACT in self.pack.facts:
            governed, found_candidates = await self._scan_targets(session, tenant_id, since, now)
            candidates += found_candidates

        stats = {
            "systems": len(systems),
            "candidates": len(discovered),
            "targets": governed,
            "detections": len(candidates),
        }
        for candidate in candidates:
            _, outcome = await self._findings.report(
                session, tenant_id, candidate, scan_run_id=scan.id
            )
            stats[outcome] = stats.get(outcome, 0) + 1
        stats["mitigated"] = await self._findings.mitigate_undetected(
            session,
            tenant_id,
            scan_run_id=scan.id,
            rule_ids=[rule.id for rule in self.pack.rules],
        )
        scan.stats = stats
        scan.finished_at = self._clock.now()
        await self._audit.append(
            session,
            tenant_id,
            AuditRecord(
                action="scan.completed",
                outcome=f"detections:{len(candidates)}",
                actor_id=actor_id,
                resource_type="scan_run",
                resource_id=str(scan.id),
            ),
        )
        await session.flush()
        return scan
