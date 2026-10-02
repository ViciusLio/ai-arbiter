"""Classification tables."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import JSON, Date, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.events.model import Event
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime


class Classification(Base):
    """What the rule pack concluded from the declared facts. Never altered.

    A change of facts or of pack produces a new row; ``superseded_by`` links to it. What
    a person decided about the result is in ``ClassificationReview`` (ADR-0037).
    """

    __tablename__ = "classification"
    __table_args__ = (Index("ix_classification_system", "tenant_id", "ai_system_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    ai_system_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("ai_system.id"))
    rulepack: Mapped[str] = mapped_column(String(100))
    rulepack_version: Mapped[str] = mapped_column(String(100))
    regulation_as_of: Mapped[date | None] = mapped_column(Date, default=None)
    tier: Mapped[str] = mapped_column(String(20))
    obligations: Mapped[list[Any]] = mapped_column(JSON, default=list)
    trace: Mapped[list[Any]] = mapped_column(JSON, default=list)
    missing_facts: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # Digest of the facts, roles and pack version: an unchanged system is not
    # classified again.
    input_digest: Mapped[str] = mapped_column(String(64))
    superseded_by: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ReviewDecision(StrEnum):
    CONFIRMED = "confirmed"
    OVERRIDDEN = "overridden"


class ClassificationReview(Base):
    """A person's decision on a classification. The reviewer appears by identifier."""

    __tablename__ = "classification_review"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    classification_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("classification.id"))
    decision: Mapped[str] = mapped_column(String(20))
    # The tier that holds after the review: the engine's when confirmed, the reviewer's
    # when overridden.
    tier: Mapped[str] = mapped_column(String(20))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid)
    reason: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SystemClassified(Event):
    event_type: ClassVar[str] = "system.classified"

    ai_system_id: UUID
    classification_id: UUID
