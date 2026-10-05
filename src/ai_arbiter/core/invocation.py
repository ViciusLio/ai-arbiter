"""The record of one call to a tool or to an agent through Arbiter (Phase 5).

Written by the MCP and A2A proxies and read by the compliance toolkit, as interactions
are for models; hence its place in the shared kernel. It holds what was called and how
it ended: never the arguments, never the result.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime


class InvocationProtocol(StrEnum):
    MCP = "mcp"
    A2A = "a2a"


class InvocationOutcome(StrEnum):
    DENIED = "denied"  # refused by Arbiter; nothing was forwarded
    FORWARDED = "forwarded"  # sent on; how it ended is not recorded yet
    OK = "ok"
    ERROR = "error"  # the other side answered with an error, or could not be reached


class Invocation(Base):
    __tablename__ = "invocation"
    __table_args__ = (Index("ix_invocation_tenant_started", "tenant_id", "started_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    team_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    project_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    principal_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    ai_system_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    protocol: Mapped[str] = mapped_column(String(10))
    # The key the caller asked for: an MCP server or an agent of the catalogue, or a
    # name that is in neither.
    target: Mapped[str] = mapped_column(String(100))
    # Whether the catalogue knew the target when the call was made.
    target_known: Mapped[bool] = mapped_column(Boolean, default=True)
    method: Mapped[str] = mapped_column(String(100))
    # The tool or the prompt called. Null for anything else: the address of a resource
    # can hold personal data and is not kept.
    name: Mapped[str | None] = mapped_column(String(200), default=None)
    outcome: Mapped[str] = mapped_column(String(20))
    # Why it was denied or failed: a rule id, or the class of an exception. Never a
    # message from the other side.
    reason: Mapped[str | None] = mapped_column(String(100), default=None)
    status_code: Mapped[int | None] = mapped_column(Integer, default=None)
    streamed: Mapped[bool] = mapped_column(Boolean, default=False)
    request_bytes: Mapped[int] = mapped_column(Integer, default=0)
    response_bytes: Mapped[int | None] = mapped_column(Integer, default=None)
    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    decision_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
