"""Finding tables."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Date, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime


class FindingStatus(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    MITIGATED = "mitigated"
    ACCEPTED = "accepted"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_ORDER = (
    Severity.CRITICAL,
    Severity.HIGH,
    Severity.MEDIUM,
    Severity.LOW,
    Severity.INFO,
)


class SuppressionScope(StrEnum):
    RULE = "rule"  # the rule, for every system
    SYSTEM = "system"  # the rule, for one system
    FINGERPRINT = "fingerprint"  # this finding only


class ScanRun(Base):
    __tablename__ = "scan_run"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    kind: Mapped[str] = mapped_column(String(20), default="inventory")
    rulepack_version: Mapped[str] = mapped_column(String(100))
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class Finding(Base):
    __tablename__ = "finding"
    __table_args__ = (
        UniqueConstraint("tenant_id", "fingerprint"),
        Index("ix_finding_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    # Null for a finding about the tenant as a whole.
    ai_system_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_system.id"), default=None
    )
    scan_run_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("scan_run.id"))
    rule_id: Mapped[str] = mapped_column(String(100))
    rulepack_version: Mapped[str] = mapped_column(String(100))
    # Rule, system and what distinguishes the evidence: a repeated detection updates the
    # finding instead of creating another.
    fingerprint: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default=FindingStatus.OPEN.value)
    message_key: Mapped[str] = mapped_column(String(200))
    legal_refs: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # When the obligation behind the finding starts to apply. Before that date the
    # finding is about readiness.
    applies_from: Mapped[date | None] = mapped_column(Date, default=None)
    accepted_until: Mapped[date | None] = mapped_column(Date, default=None)
    first_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    occurrences: Mapped[int] = mapped_column(Integer, default=1)


class FindingEvidence(Base):
    """What the scan observed. Counts, identifiers and names of things, never content."""

    __tablename__ = "finding_evidence"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    finding_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("finding.id"))
    kind: Mapped[str] = mapped_column(String(50))
    source_ref: Mapped[str] = mapped_column(String(200), default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    collected_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class FindingReview(Base):
    """A change of status. ``reviewer_id`` is null when the scanner made it."""

    __tablename__ = "finding_review"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    finding_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("finding.id"))
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reviewer_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    reason: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Suppression(Base):
    __tablename__ = "suppression"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    rule_id: Mapped[str] = mapped_column(String(100))
    scope_type: Mapped[str] = mapped_column(String(20))
    # Empty for the rule scope; a system id or a fingerprint for the other two.
    scope_ref: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(2000))
    created_by: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)


class DigestRun(Base):
    __tablename__ = "digest_run"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    period_start: Mapped[datetime] = mapped_column(UTCDateTime)
    period_end: Mapped[datetime] = mapped_column(UTCDateTime)
    locales: Mapped[list[Any]] = mapped_column(JSON, default=list)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
