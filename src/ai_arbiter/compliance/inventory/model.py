"""Inventory tables."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import JSON, Date, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.events.model import Event
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime


class Origin(StrEnum):
    DECLARED = "declared"
    DISCOVERED = "discovered"  # seen in traffic, not declared yet (v0.1.x)


class Lifecycle(StrEnum):
    PLANNED = "planned"
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    RETIRED = "retired"


class AISystem(Base):
    __tablename__ = "ai_system"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    # Chosen by the organisation; stable across changes to the declaration.
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    purpose: Mapped[str] = mapped_column(String(2000), default="")
    origin: Mapped[str] = mapped_column(String(20), default=Origin.DECLARED.value)
    lifecycle: Mapped[str] = mapped_column(String(20), default=Lifecycle.PRODUCTION.value)
    owner_principal_id: Mapped[UUID | None] = mapped_column(Uuid, default=None)
    # The facts declared about the system. Which facts exist is set by the rule packs,
    # not by columns, so a new pack can ask new questions without a migration.
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    models_used: Mapped[list[Any]] = mapped_column(JSON, default=list)
    declared_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AISystemRole(Base):
    """An AI Act role the organisation holds for a system (ADR-0022)."""

    __tablename__ = "ai_system_role"
    __table_args__ = (UniqueConstraint("ai_system_id", "role"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    ai_system_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("ai_system.id"))
    role: Mapped[str] = mapped_column(String(40))
    basis: Mapped[str] = mapped_column(String(500), default="")
    since: Mapped[date | None] = mapped_column(Date, default=None)


class AISystemProject(Base):
    """A project of the gateway whose requests belong to a system (ADR-0059).

    A system may name several projects, and a project may be named by several systems.
    """

    __tablename__ = "ai_system_project"
    __table_args__ = (UniqueConstraint("ai_system_id", "project_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    ai_system_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("ai_system.id"))
    project_id: Mapped[UUID] = mapped_column(Uuid, index=True)


class SystemDeclared(Event):
    event_type: ClassVar[str] = "system.declared"

    ai_system_id: UUID


class SystemChanged(Event):
    event_type: ClassVar[str] = "system.changed"

    ai_system_id: UUID
