"""Event envelope and its outbox row."""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime


class Event(BaseModel):
    """Base class of every event.

    Subclasses set ``event_type`` to a stable name; it is what the outbox stores, so
    renaming it is a breaking change. Payloads carry identifiers, never content.
    """

    model_config = ConfigDict(frozen=True)

    event_type: ClassVar[str]

    id: UUID = Field(default_factory=new_id)
    tenant_id: UUID
    occurred_at: datetime = Field(default_factory=utcnow)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        if not isinstance(getattr(cls, "event_type", None), str):
            raise TypeError(f"{cls.__name__} must define event_type")


class OutboxEvent(Base):
    """An event waiting to be delivered, written with the change that caused it."""

    __tablename__ = "outbox_event"
    # The dispatcher scans for undelivered rows across tenants, oldest first.
    __table_args__ = (Index("ix_outbox_event_pending", "dispatched_at", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Exception class name only: messages can carry content and are never stored.
    last_error: Mapped[str | None] = mapped_column(String(200), default=None)
