"""A2A registry tables: the agents an organisation knows, and who may call them."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime

# The state of an agent whose card was never read.
NOT_FETCHED = "not_fetched"


class A2aAgent(Base):
    __tablename__ = "a2a_agent"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    # Chosen by the organisation; the proxy serves the agent under this name.
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    # Where its Agent Card is read from.
    card_url: Mapped[str] = mapped_column(String(2000))
    # The declared AI system the agent belongs to. The table belongs to the compliance
    # toolkit and is named here by string: the gateway does not import it.
    ai_system_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_system.id"), default=None
    )
    # A secret reference (secret://NAME) for the credential sent to the agent.
    credential: Mapped[str | None] = mapped_column(String(200), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # What the card said when it was last read. The card itself is not kept: its
    # description and its skills are text written by whoever runs the agent.
    card_name: Mapped[str | None] = mapped_column(String(200), default=None)
    card_version: Mapped[str | None] = mapped_column(String(50), default=None)
    card_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    # Each: the protocol binding, the URL and the protocol version.
    interfaces: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # verified, unsigned, unknown_key, invalid, or not_fetched (ADR-0053).
    verification: Mapped[str] = mapped_column(String(20), default=NOT_FETCHED)
    signing_key_id: Mapped[str | None] = mapped_column(String(200), default=None)
    fetched_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class A2aGrant(Base):
    """Permission for a project, an AI system or the whole tenant to call an agent."""

    __tablename__ = "a2a_grant"
    __table_args__ = (UniqueConstraint("agent_id", "scope_type", "scope_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    agent_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("a2a_agent.id"))
    scope_type: Mapped[str] = mapped_column(String(20))
    scope_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
