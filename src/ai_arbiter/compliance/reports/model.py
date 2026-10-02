"""What the reports say, gathered from the database. Rendering is separate."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.findings.model import SEVERITY_ORDER, Finding
from ai_arbiter.compliance.inventory.model import AISystem, AISystemRole
from ai_arbiter.compliance.runtime import ComplianceRuntime
from ai_arbiter.core.audit import DatabaseAuditLog, VerificationReport
from ai_arbiter.core.audit.model import AuditEntry
from ai_arbiter.core.persistence.tenant import Tenant

MAX_AUDIT_ENTRIES = 500


@dataclass(frozen=True)
class ReportObligation:
    message_key: str
    legal_refs: tuple[str, ...]
    roles: tuple[str, ...]
    applies_from: date | None
    applicable: bool
    addressed_to_us: bool


@dataclass(frozen=True)
class ReportClassification:
    created_at: datetime
    tier: str
    rulepack_version: str
    current: bool


@dataclass(frozen=True)
class SystemReport:
    tenant_name: str
    generated_at: datetime
    system: AISystem
    roles: Sequence[AISystemRole]
    tier: str | None
    engine_tier: str | None
    review_status: str
    review_reason: str
    rulepack: str
    rulepack_version: str
    regulation_as_of: date | None
    pack_review: str | None
    obligations: Sequence[ReportObligation]
    missing_facts: Sequence[str]
    history: Sequence[ReportClassification]
    findings: Sequence[Finding]
    traffic: Mapping[str, Any]


@dataclass(frozen=True)
class AuditReport:
    tenant_name: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    verification: VerificationReport
    actions: Sequence[tuple[str, int]]
    entries: Sequence[AuditEntry]
    total_in_period: int

    @property
    def truncated(self) -> bool:
        return self.total_in_period > len(self.entries)


async def build_system_report(
    session: AsyncSession, tenant: Tenant, compliance: ComplianceRuntime, key: str
) -> SystemReport:
    """Everything recorded about one system: declaration, classification, findings, traffic."""
    now = compliance.clock.now()
    system = await compliance.inventory.get(session, tenant.id, key)
    current = await compliance.classifier.current(session, tenant.id, system.id)
    history = await compliance.classifier.history(session, tenant.id, system.id)
    obligations: list[ReportObligation] = []
    if current is not None:
        for item in current.classification.obligations:
            applies = date.fromisoformat(item["applies_from"]) if item.get("applies_from") else None
            obligations.append(
                ReportObligation(
                    message_key=item["message_key"],
                    legal_refs=tuple(item.get("legal_refs") or ()),
                    roles=tuple(item.get("roles") or ()),
                    applies_from=applies,
                    applicable=applies is None or applies <= now.date(),
                    addressed_to_us=bool(item.get("applies_to_declared_roles")),
                )
            )
    rank = {severity.value: position for position, severity in enumerate(SEVERITY_ORDER)}
    findings = sorted(
        await compliance.findings.list(session, tenant.id, ai_system_id=system.id),
        key=lambda finding: (
            finding.status not in ("open", "confirmed"),
            rank.get(finding.severity, 99),
        ),
    )
    _, traffic = await compliance.scanner.observe(session, system)
    regulation = compliance.ai_act_pack.regulation
    return SystemReport(
        tenant_name=tenant.name,
        generated_at=now,
        system=system,
        roles=await compliance.inventory.roles(session, system),
        tier=current.tier.value if current else None,
        engine_tier=current.classification.tier if current else None,
        review_status=current.status if current else "not_classified",
        review_reason=current.review.reason if current and current.review else "",
        rulepack=current.classification.rulepack if current else compliance.ai_act_pack.pack,
        rulepack_version=(
            current.classification.rulepack_version if current else compliance.ai_act_pack.version
        ),
        regulation_as_of=current.classification.regulation_as_of if current else None,
        pack_review=regulation.review if regulation else None,
        obligations=obligations,
        missing_facts=list(current.classification.missing_facts) if current else [],
        history=[
            ReportClassification(
                created_at=item.created_at,
                tier=item.tier,
                rulepack_version=item.rulepack_version,
                current=item.superseded_by is None,
            )
            for item in history
        ],
        findings=findings,
        traffic=traffic,
    )


async def build_audit_report(
    session: AsyncSession,
    tenant: Tenant,
    audit: DatabaseAuditLog,
    *,
    period_start: datetime,
    period_end: datetime,
    generated_at: datetime,
) -> AuditReport:
    """The audit log over a period: whether the whole chain verifies, and what happened."""
    in_period = (
        AuditEntry.tenant_id == tenant.id,
        AuditEntry.occurred_at >= period_start,
        AuditEntry.occurred_at < period_end,
    )
    actions = [
        (str(action), int(count))
        for action, count in await session.execute(
            select(AuditEntry.action, func.count())
            .where(*in_period)
            .group_by(AuditEntry.action)
            .order_by(AuditEntry.action)
        )
    ]
    entries = (
        await session.scalars(
            select(AuditEntry).where(*in_period).order_by(AuditEntry.seq).limit(MAX_AUDIT_ENTRIES)
        )
    ).all()
    return AuditReport(
        tenant_name=tenant.name,
        generated_at=generated_at,
        period_start=period_start,
        period_end=period_end,
        verification=await audit.verify(session, tenant.id),
        actions=actions,
        entries=entries,
        total_in_period=sum(count for _, count in actions),
    )
