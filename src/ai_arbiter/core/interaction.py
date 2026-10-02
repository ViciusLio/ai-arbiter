"""The canonical record of one model interaction (ADR-0019).

Written by Arbiter's own gateway and, later, by the importers of external gateways, and
read by FinOps and by the compliance toolkit; hence its place in the shared kernel. It
holds metadata only: no prompt and no completion text (ADR-0018).
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.events.model import Event
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import DecimalAmount, UTCDateTime

NATIVE_SOURCE = "native"


class InteractionStatus(StrEnum):
    OK = "ok"
    DENIED = "denied"  # stopped by policy before any provider was called
    ERROR = "error"  # no provider could complete it
    ABORTED = "aborted"  # a stream that ended before its last chunk


class Interaction(Base):
    __tablename__ = "interaction"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "source_record_id"),
        Index("ix_interaction_tenant_started", "tenant_id", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    team_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    project_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    principal_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    ai_system_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    # ``native`` for Arbiter's gateway, otherwise the name of the external source.
    source: Mapped[str] = mapped_column(String(50), default=NATIVE_SOURCE)
    source_record_id: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    operation: Mapped[str] = mapped_column(String(30), default="chat")
    requested_model: Mapped[str | None] = mapped_column(String(200), default=None)
    deployment: Mapped[str | None] = mapped_column(String(200), default=None)
    provider: Mapped[str | None] = mapped_column(String(100), default=None)
    model: Mapped[str | None] = mapped_column(String(200), default=None)
    region: Mapped[str | None] = mapped_column(String(100), default=None)
    status: Mapped[str] = mapped_column(String(20))
    streamed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Unknown when the provider reported no usage and no estimate was asked for (ADR-0031).
    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    usage_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    # An estimate from the price catalogue; null when the model has no price.
    cost_estimate: Mapped[Decimal | None] = mapped_column(DecimalAmount, default=None)
    currency: Mapped[str | None] = mapped_column(String(3), default=None)
    price_version: Mapped[str | None] = mapped_column(String(100), default=None)
    policy_outcome: Mapped[str | None] = mapped_column(String(50), default=None)
    # Keyed fingerprint of the prompt (ADR-0018); null when no key is configured.
    prompt_fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)
    # Categories of personal data found in the prompt. Never the values.
    pii_categories: Mapped[list[Any]] = mapped_column(JSON, default=list)
    decision_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)


class InteractionRecorded(Event):
    """Published when an interaction is stored. Carries its identifier, nothing else."""

    event_type: ClassVar[str] = "interaction.recorded"

    interaction_id: UUID
