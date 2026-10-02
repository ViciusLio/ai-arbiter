"""The canonical record of one model interaction (ADR-0019).

Written by Arbiter's own gateway and, later, by the importers of external gateways, and
read by FinOps and by the compliance toolkit; hence its place in the shared kernel. It
holds metadata only: no prompt and no completion text (ADR-0018).
"""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, ClassVar, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
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
    # What an external source groups its requests by: a team or an application, never
    # a person. Lets undeclared use be told apart by who makes it (ADR-0042).
    source_group: Mapped[str | None] = mapped_column(String(200), default=None)
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


class InteractionRecord(BaseModel):
    """An interaction as a source outside Arbiter's gateway reports it (ADR-0019).

    This is also the canonical JSONL format of ``arbiter ingest``: one such object per
    line. It has no field for prompt or completion text: a source adapter drops content
    before a record exists. Missing fields stay missing.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,49}$")
    source_record_id: str = Field(min_length=1, max_length=100)
    started_at: AwareDatetime
    duration_ms: int | None = Field(default=None, ge=0)
    operation: str = Field(default="chat", max_length=30)
    requested_model: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    region: str | None = Field(default=None, max_length=100)
    status: InteractionStatus = InteractionStatus.OK
    streamed: bool = False
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    usage_estimated: bool = False
    # A decimal written as a string, as the source computed it, with its currency.
    cost_estimate: str | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    pii_categories: list[str] = Field(default_factory=list)
    # Key of the declared AI system the record belongs to, when the source says so.
    system: str | None = None
    # The team or the application the request came from at the source. Not a person:
    # a source adapter leaves it empty when all it has is the name of a user.
    group: str | None = Field(default=None, min_length=1, max_length=200)
    # What a configured mapping can match on, for example the alias of the key or of
    # the team at the source. Used to attribute the record, then discarded.
    labels: dict[str, str] = Field(default_factory=dict)

    @field_validator("source")
    @classmethod
    def _not_native(cls, value: str) -> str:
        if value == NATIVE_SOURCE:
            raise ValueError("'native' is reserved for Arbiter's own gateway")
        return value

    @field_validator("cost_estimate")
    @classmethod
    def _decimal(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                amount = Decimal(value)
            except InvalidOperation:
                amount = Decimal("NaN")
            if not amount.is_finite() or amount < 0:
                raise ValueError("cost_estimate must be a decimal number, zero or more")
        return value


class TelemetrySource(Protocol):
    """Turns one record of an external gateway into the canonical record.

    Implemented by source plugins, registered under ``ai_arbiter.telemetry_sources``.
    ``parse`` performs the minimisation: content is dropped, personal identifiers are
    not carried over. It raises ``ValueError`` for a record it cannot read.
    """

    name: str
    # What the mapping was written and checked against.
    tested_against: str

    def parse(self, payload: Mapping[str, Any]) -> InteractionRecord: ...
