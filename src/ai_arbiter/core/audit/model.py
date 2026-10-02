"""Audit tables (ADR-0017)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, BigInteger, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime


class AuditChainHead(Base):
    """The last link of a tenant's chain. Locked while an entry is appended."""

    __tablename__ = "audit_chain_head"

    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"), primary_key=True)
    last_seq: Mapped[int] = mapped_column(BigInteger)
    last_hash: Mapped[str] = mapped_column(String(64))


class AuditEntry(Base):
    """One link. Holds identifiers and outcomes, never content and never names."""

    __tablename__ = "audit_entry"
    __table_args__ = (UniqueConstraint("tenant_id", "seq"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    seq: Mapped[int] = mapped_column(BigInteger)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    action: Mapped[str] = mapped_column(String(100))
    resource_type: Mapped[str | None] = mapped_column(String(50), default=None)
    resource_id: Mapped[str | None] = mapped_column(String(64), default=None)
    outcome: Mapped[str] = mapped_column(String(100))
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))
