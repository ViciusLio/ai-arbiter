"""What a digest says, gathered from the database. Rendering is separate."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.classifier.service import ClassifierService
from ai_arbiter.compliance.findings.model import (
    SEVERITY_ORDER,
    DigestRun,
    Finding,
    FindingReview,
)
from ai_arbiter.compliance.findings.service import ACTIVE, FindingService
from ai_arbiter.compliance.inventory.model import AISystem
from ai_arbiter.core.audit.model import AuditChainHead
from ai_arbiter.core.domain.risk import RiskTier
from ai_arbiter.core.interaction import Interaction, InteractionStatus
from ai_arbiter.core.persistence.tenant import Tenant

TIER_ORDER = (
    RiskTier.PROHIBITED,
    RiskTier.HIGH_RISK,
    RiskTier.TRANSPARENCY,
    RiskTier.MINIMAL,
    RiskTier.OUT_OF_SCOPE,
    RiskTier.UNDETERMINED,
)
NOT_CLASSIFIED = "not_classified"


@dataclass(frozen=True)
class DigestSystem:
    key: str
    name: str
    tier: str
    # proposed, confirmed, overridden, or not_classified
    status: str
    missing_facts: int


@dataclass(frozen=True)
class DigestFinding:
    rule_id: str
    severity: str
    status: str
    system_key: str | None
    message_key: str
    legal_refs: tuple[str, ...]
    applies_from: date | None
    # The obligation behind the finding does not apply yet.
    readiness: bool
    first_seen: datetime


@dataclass(frozen=True)
class DigestTraffic:
    requests: int = 0
    denied: int = 0
    failed: int = 0
    cost: Mapping[str, Decimal] = field(default_factory=dict)
    unpriced: int = 0


@dataclass(frozen=True)
class DigestModel:
    tenant_name: str
    period_start: datetime
    period_end: datetime
    generated_at: datetime
    pack: str
    pack_version: str
    pack_as_of: date | None
    pack_review: str | None
    systems: Sequence[DigestSystem]
    findings: Sequence[DigestFinding]
    opened_in_period: int
    closed_in_period: int
    traffic: DigestTraffic
    rule_feedback: Mapping[str, Mapping[str, int]]
    audit_seq: int
    audit_hash: str | None

    @property
    def tier_counts(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for system in self.systems:
            counts[system.tier] = counts.get(system.tier, 0) + 1
        order = [tier.value for tier in TIER_ORDER] + [NOT_CLASSIFIED]
        return [(tier, counts[tier]) for tier in order if tier in counts]

    @property
    def awaiting_review(self) -> int:
        return sum(1 for system in self.systems if system.status == "proposed")

    @property
    def severity_counts(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return [(s.value, counts[s.value]) for s in SEVERITY_ORDER if s.value in counts]

    def summary(self) -> dict[str, Any]:
        """Counts only, for the record of the run."""
        return {
            "systems": len(self.systems),
            "tiers": dict(self.tier_counts),
            "awaiting_review": self.awaiting_review,
            "active_findings": len(self.findings),
            "severities": dict(self.severity_counts),
            "opened_in_period": self.opened_in_period,
            "closed_in_period": self.closed_in_period,
            "requests": self.traffic.requests,
            "audit_seq": self.audit_seq,
        }


async def build_digest(
    session: AsyncSession,
    tenant: Tenant,
    *,
    classifier: ClassifierService,
    findings: FindingService,
    period_start: datetime,
    period_end: datetime,
    generated_at: datetime,
) -> DigestModel:
    """Gather the digest of a tenant for a period. Reads only."""
    systems = (
        await session.scalars(
            select(AISystem).where(AISystem.tenant_id == tenant.id).order_by(AISystem.key)
        )
    ).all()
    keys = {system.id: system.key for system in systems}
    digest_systems: list[DigestSystem] = []
    for system in systems:
        current = await classifier.current(session, tenant.id, system.id)
        digest_systems.append(
            DigestSystem(
                key=system.key,
                name=system.name,
                tier=current.tier.value if current else NOT_CLASSIFIED,
                status=current.status if current else NOT_CLASSIFIED,
                missing_facts=len(current.classification.missing_facts) if current else 0,
            )
        )

    today = generated_at.date()
    severity_rank = {severity.value: rank for rank, severity in enumerate(SEVERITY_ORDER)}
    active = sorted(
        await findings.list(session, tenant.id, statuses=list(ACTIVE)),
        key=lambda f: (
            severity_rank.get(f.severity, 99),
            keys.get(f.ai_system_id or tenant.id, ""),
        ),
    )
    digest_findings = [
        DigestFinding(
            rule_id=finding.rule_id,
            severity=finding.severity,
            status=finding.status,
            system_key=keys.get(finding.ai_system_id) if finding.ai_system_id else None,
            message_key=finding.message_key,
            legal_refs=tuple(
                str(ref.get("article")) for ref in finding.legal_refs if isinstance(ref, Mapping)
            ),
            applies_from=finding.applies_from,
            readiness=finding.applies_from is not None and finding.applies_from > today,
            first_seen=finding.first_seen,
        )
        for finding in active
    ]
    in_period = (Finding.first_seen >= period_start, Finding.first_seen < period_end)
    opened = int(
        await session.scalar(
            select(func.count())
            .select_from(Finding)
            .where(Finding.tenant_id == tenant.id, *in_period)
        )
        or 0
    )
    closed = int(
        await session.scalar(
            select(func.count())
            .select_from(FindingReview)
            .where(
                FindingReview.tenant_id == tenant.id,
                FindingReview.created_at >= period_start,
                FindingReview.created_at < period_end,
                FindingReview.to_status.not_in(ACTIVE),
            )
        )
        or 0
    )

    window = (
        Interaction.tenant_id == tenant.id,
        Interaction.started_at >= period_start,
        Interaction.started_at < period_end,
    )
    by_status = {
        status: int(count)
        for status, count in await session.execute(
            select(Interaction.status, func.count()).where(*window).group_by(Interaction.status)
        )
    }
    cost = {
        str(currency): Decimal(total)
        for currency, total in await session.execute(
            select(Interaction.currency, func.sum(Interaction.cost_estimate))
            .where(*window, Interaction.currency.is_not(None))
            .group_by(Interaction.currency)
        )
        if total is not None
    }
    completed = (InteractionStatus.OK.value, InteractionStatus.ABORTED.value)
    unpriced = int(
        await session.scalar(
            select(func.count()).where(
                *window, Interaction.status.in_(completed), Interaction.cost_estimate.is_(None)
            )
        )
        or 0
    )
    head = await session.scalar(select(AuditChainHead).where(AuditChainHead.tenant_id == tenant.id))
    pack = classifier.pack
    return DigestModel(
        tenant_name=tenant.name,
        period_start=period_start,
        period_end=period_end,
        generated_at=generated_at,
        pack=pack.pack,
        pack_version=pack.version,
        pack_as_of=pack.regulation.as_of if pack.regulation else None,
        pack_review=pack.regulation.review if pack.regulation else None,
        systems=digest_systems,
        findings=digest_findings,
        opened_in_period=opened,
        closed_in_period=closed,
        traffic=DigestTraffic(
            requests=sum(by_status.values()),
            denied=by_status.get(InteractionStatus.DENIED.value, 0),
            failed=by_status.get(InteractionStatus.ERROR.value, 0),
            cost=cost,
            unpriced=unpriced,
        ),
        rule_feedback=await findings.rule_feedback(session, tenant.id),
        audit_seq=head.last_seq if head else 0,
        audit_hash=head.last_hash if head and head.last_seq else None,
    )


async def record_digest_run(
    session: AsyncSession, tenant: Tenant, digest: DigestModel, locales: Sequence[str]
) -> DigestRun:
    run = DigestRun(
        tenant_id=tenant.id,
        period_start=digest.period_start,
        period_end=digest.period_end,
        locales=list(locales),
        summary=digest.summary(),
        generated_at=digest.generated_at,
    )
    session.add(run)
    await session.flush()
    return run
