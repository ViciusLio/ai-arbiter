"""Finding lifecycle: report, deduplicate, suppress, review."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.findings.model import (
    Finding,
    FindingEvidence,
    FindingReview,
    FindingStatus,
    Suppression,
    SuppressionScope,
)
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.canonical_json import sha256_hex
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.errors import ConflictError, NotFoundError
from ai_arbiter.core.ports import AuditLog

MIN_REASON_LENGTH = 10

# What a person may do (flows.md, section 6). The scanner makes two more moves on its
# own: it reopens a mitigated finding that is detected again, and marks as mitigated a
# finding that is no longer detected.
TRANSITIONS: Mapping[FindingStatus, frozenset[FindingStatus]] = {
    FindingStatus.OPEN: frozenset(
        {FindingStatus.CONFIRMED, FindingStatus.FALSE_POSITIVE, FindingStatus.ACCEPTED}
    ),
    FindingStatus.CONFIRMED: frozenset({FindingStatus.MITIGATED, FindingStatus.ACCEPTED}),
    FindingStatus.MITIGATED: frozenset({FindingStatus.OPEN}),
    FindingStatus.FALSE_POSITIVE: frozenset({FindingStatus.OPEN}),
    FindingStatus.ACCEPTED: frozenset({FindingStatus.OPEN}),
}
_NEEDS_REASON = frozenset({FindingStatus.FALSE_POSITIVE, FindingStatus.ACCEPTED})
ACTIVE = (FindingStatus.OPEN.value, FindingStatus.CONFIRMED.value)

Reported = Literal["opened", "refreshed", "reopened", "suppressed", "unchanged"]


@dataclass(frozen=True)
class Evidence:
    kind: str
    source_ref: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FindingCandidate:
    rule_id: str
    rulepack_version: str
    severity: str
    message_key: str
    ai_system_id: UUID | None = None
    # What tells this detection apart from another by the same rule on the same system.
    distinguishing: str = ""
    legal_refs: Sequence[Mapping[str, str]] = ()
    applies_from: date | None = None
    evidence: Sequence[Evidence] = ()

    @property
    def fingerprint(self) -> str:
        return sha256_hex(
            {
                "rule": self.rule_id,
                "system": str(self.ai_system_id) if self.ai_system_id else None,
                "distinguishing": self.distinguishing,
            }
        )


@dataclass(frozen=True)
class FindingDetail:
    finding: Finding
    evidence: Sequence[FindingEvidence]
    reviews: Sequence[FindingReview]


class FindingService:
    def __init__(self, audit: AuditLog, clock: Clock | None = None) -> None:
        self._audit = audit
        self._clock = clock if clock is not None else SystemClock()

    # Reporting, by the scanner

    async def _suppressed(
        self, session: AsyncSession, tenant_id: UUID, candidate: FindingCandidate
    ) -> bool:
        now = self._clock.now()
        suppressions = await session.scalars(
            select(Suppression).where(
                Suppression.tenant_id == tenant_id, Suppression.rule_id == candidate.rule_id
            )
        )
        for suppression in suppressions:
            if suppression.expires_at is not None and suppression.expires_at <= now:
                continue
            if suppression.scope_type == SuppressionScope.RULE.value:
                return True
            target = (
                str(candidate.ai_system_id)
                if suppression.scope_type == SuppressionScope.SYSTEM.value
                else candidate.fingerprint
            )
            if suppression.scope_ref == target:
                return True
        return False

    async def _move(
        self,
        session: AsyncSession,
        finding: Finding,
        to: FindingStatus,
        *,
        reviewer_id: UUID | None,
        reason: str,
    ) -> None:
        session.add(
            FindingReview(
                tenant_id=finding.tenant_id,
                finding_id=finding.id,
                from_status=finding.status,
                to_status=to.value,
                reviewer_id=reviewer_id,
                reason=reason,
                created_at=self._clock.now(),
            )
        )
        finding.status = to.value
        await session.flush()
        await self._audit.append(
            session,
            finding.tenant_id,
            AuditRecord(
                action=f"finding.{to.value}",
                outcome=finding.rule_id,
                actor_id=reviewer_id,
                resource_type="finding",
                resource_id=str(finding.id),
            ),
        )

    async def report(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        candidate: FindingCandidate,
        *,
        scan_run_id: UUID,
    ) -> tuple[Finding | None, Reported]:
        """Record a detection. Returns the finding and what happened to it."""
        if await self._suppressed(session, tenant_id, candidate):
            return None, "suppressed"
        now = self._clock.now()
        finding = await session.scalar(
            select(Finding).where(
                Finding.tenant_id == tenant_id, Finding.fingerprint == candidate.fingerprint
            )
        )
        outcome: Reported
        if finding is None:
            finding = Finding(
                tenant_id=tenant_id,
                ai_system_id=candidate.ai_system_id,
                scan_run_id=scan_run_id,
                rule_id=candidate.rule_id,
                rulepack_version=candidate.rulepack_version,
                fingerprint=candidate.fingerprint,
                severity=candidate.severity,
                status=FindingStatus.OPEN.value,
                message_key=candidate.message_key,
                legal_refs=[dict(ref) for ref in candidate.legal_refs],
                applies_from=candidate.applies_from,
                first_seen=now,
                last_seen=now,
                occurrences=1,
            )
            session.add(finding)
            await session.flush()
            await self._audit.append(
                session,
                tenant_id,
                AuditRecord(
                    action="finding.opened",
                    outcome=candidate.rule_id,
                    resource_type="finding",
                    resource_id=str(finding.id),
                ),
            )
            outcome = "opened"
        else:
            outcome = "refreshed"
            expired = (
                finding.status == FindingStatus.ACCEPTED.value
                and finding.accepted_until is not None
                and finding.accepted_until < now.date()
            )
            if finding.status == FindingStatus.MITIGATED.value or expired:
                reason = "acceptance expired" if expired else "detected again"
                finding.accepted_until = None
                await self._move(
                    session, finding, FindingStatus.OPEN, reviewer_id=None, reason=reason
                )
                outcome = "reopened"
            elif finding.status not in ACTIVE:
                # A false positive or an accepted risk stays as the reviewer left it.
                outcome = "unchanged"
            finding.scan_run_id = scan_run_id
            finding.last_seen = now
            finding.occurrences += 1
            finding.severity = candidate.severity
            finding.rulepack_version = candidate.rulepack_version
            await session.execute(
                delete(FindingEvidence).where(FindingEvidence.finding_id == finding.id)
            )
        for item in candidate.evidence:
            session.add(
                FindingEvidence(
                    tenant_id=tenant_id,
                    finding_id=finding.id,
                    kind=item.kind,
                    source_ref=item.source_ref,
                    data=dict(item.data),
                    collected_at=now,
                )
            )
        await session.flush()
        return finding, outcome

    async def mitigate_undetected(
        self, session: AsyncSession, tenant_id: UUID, *, scan_run_id: UUID, rule_ids: Sequence[str]
    ) -> int:
        """Mark as mitigated the active findings of these rules that this scan did not see."""
        stale = (
            await session.scalars(
                select(Finding).where(
                    Finding.tenant_id == tenant_id,
                    Finding.rule_id.in_(rule_ids),
                    Finding.status.in_(ACTIVE),
                    Finding.scan_run_id != scan_run_id,
                )
            )
        ).all()
        for finding in stale:
            await self._move(
                session,
                finding,
                FindingStatus.MITIGATED,
                reviewer_id=None,
                reason="no longer detected",
            )
        return len(stale)

    # Review, by a person

    async def get(self, session: AsyncSession, tenant_id: UUID, finding_id: UUID) -> FindingDetail:
        finding = await session.scalar(
            select(Finding).where(Finding.tenant_id == tenant_id, Finding.id == finding_id)
        )
        if finding is None:
            raise NotFoundError(f"finding {finding_id} not found")
        evidence = (
            await session.scalars(
                select(FindingEvidence)
                .where(FindingEvidence.finding_id == finding.id)
                .order_by(FindingEvidence.id)
            )
        ).all()
        reviews = (
            await session.scalars(
                select(FindingReview)
                .where(FindingReview.finding_id == finding.id)
                .order_by(FindingReview.created_at, FindingReview.id)
            )
        ).all()
        return FindingDetail(finding, evidence, reviews)

    async def list(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        statuses: Sequence[str] | None = None,
        ai_system_id: UUID | None = None,
    ) -> Sequence[Finding]:
        query = select(Finding).where(Finding.tenant_id == tenant_id)
        if statuses:
            query = query.where(Finding.status.in_(statuses))
        if ai_system_id is not None:
            query = query.where(Finding.ai_system_id == ai_system_id)
        return (await session.scalars(query.order_by(Finding.first_seen, Finding.id))).all()

    async def transition(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        finding_id: UUID,
        to: FindingStatus,
        *,
        reviewer_id: UUID,
        reason: str = "",
        accepted_until: date | None = None,
        suppress: SuppressionScope | None = None,
    ) -> Finding:
        """Change the status of a finding. Who, when and why are recorded and audited."""
        finding = (await self.get(session, tenant_id, finding_id)).finding
        current = FindingStatus(finding.status)
        if to not in TRANSITIONS[current]:
            allowed = ", ".join(sorted(status.value for status in TRANSITIONS[current]))
            raise ConflictError(
                f"a finding that is {current.value} cannot become {to.value} (allowed: {allowed})"
            )
        reason = reason.strip()
        if to in _NEEDS_REASON and len(reason) < MIN_REASON_LENGTH:
            raise ConflictError(
                f"marking a finding as {to.value} needs a reason of at least "
                f"{MIN_REASON_LENGTH} characters"
            )
        if to is FindingStatus.ACCEPTED:
            if accepted_until is None or accepted_until <= self._clock.now().date():
                raise ConflictError("accepting a risk needs an expiry date in the future")
            finding.accepted_until = accepted_until
        else:
            finding.accepted_until = None
        if suppress is not None and to is not FindingStatus.FALSE_POSITIVE:
            raise ConflictError("a suppression can only be created with a false positive")
        await self._move(session, finding, to, reviewer_id=reviewer_id, reason=reason)
        if suppress is not None:
            await self.suppress(
                session,
                tenant_id,
                rule_id=finding.rule_id,
                scope=suppress,
                scope_ref=(
                    ""
                    if suppress is SuppressionScope.RULE
                    else str(finding.ai_system_id)
                    if suppress is SuppressionScope.SYSTEM
                    else finding.fingerprint
                ),
                reason=reason,
                created_by=reviewer_id,
            )
        return finding

    # Suppressions

    async def suppress(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        rule_id: str,
        scope: SuppressionScope,
        scope_ref: str = "",
        reason: str,
        created_by: UUID | None,
        expires_at: Any = None,
    ) -> Suppression:
        if len(reason.strip()) < MIN_REASON_LENGTH:
            raise ConflictError(
                f"a suppression needs a reason of at least {MIN_REASON_LENGTH} characters"
            )
        if scope is not SuppressionScope.RULE and not scope_ref:
            raise ConflictError(f"a suppression scoped to a {scope.value} needs its reference")
        suppression = Suppression(
            tenant_id=tenant_id,
            rule_id=rule_id,
            scope_type=scope.value,
            scope_ref="" if scope is SuppressionScope.RULE else scope_ref,
            reason=reason.strip(),
            created_by=created_by,
            created_at=self._clock.now(),
            expires_at=expires_at,
        )
        session.add(suppression)
        await session.flush()
        await self._audit.append(
            session,
            tenant_id,
            AuditRecord(
                action="suppression.created",
                outcome=rule_id,
                actor_id=created_by,
                resource_type="suppression",
                resource_id=str(suppression.id),
            ),
        )
        return suppression

    async def suppressions(self, session: AsyncSession, tenant_id: UUID) -> Sequence[Suppression]:
        return (
            await session.scalars(
                select(Suppression)
                .where(Suppression.tenant_id == tenant_id)
                .order_by(Suppression.created_at, Suppression.id)
            )
        ).all()

    async def remove_suppression(
        self, session: AsyncSession, tenant_id: UUID, suppression_id: UUID, *, actor_id: UUID | None
    ) -> None:
        suppression = await session.scalar(
            select(Suppression).where(
                Suppression.tenant_id == tenant_id, Suppression.id == suppression_id
            )
        )
        if suppression is None:
            raise NotFoundError(f"suppression {suppression_id} not found")
        await session.delete(suppression)
        await self._audit.append(
            session,
            tenant_id,
            AuditRecord(
                action="suppression.removed",
                outcome=suppression.rule_id,
                actor_id=actor_id,
                resource_type="suppression",
                resource_id=str(suppression_id),
            ),
        )

    async def rule_feedback(
        self, session: AsyncSession, tenant_id: UUID
    ) -> Mapping[str, Mapping[str, int]]:
        """Per rule, how many findings reviewers confirmed and how many they rejected.

        This is the feedback loop of v0.1: it tells a person which rule to fix.
        """
        rows = await session.execute(
            select(Finding.rule_id, Finding.status, func.count())
            .where(Finding.tenant_id == tenant_id)
            .group_by(Finding.rule_id, Finding.status)
        )
        feedback: dict[str, dict[str, int]] = {}
        for rule_id, status, count in rows:
            feedback.setdefault(rule_id, {})[status] = int(count)
        return feedback
