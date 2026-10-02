"""Identity tables: who belongs to a tenant and what they may do."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime


class PrincipalKind(StrEnum):
    USER = "user"
    SERVICE = "service"


class ScopeType(StrEnum):
    """What a role binding, a budget or a usage figure refers to."""

    TENANT = "tenant"
    TEAM = "team"
    PROJECT = "project"
    PRINCIPAL = "principal"
    AI_SYSTEM = "ai_system"


class Team(Base):
    __tablename__ = "team"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Project(Base):
    __tablename__ = "project"
    __table_args__ = (UniqueConstraint("tenant_id", "team_id", "name"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    team_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("team.id"))
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Principal(Base):
    """A person or a service. ``display_name`` is the only personal datum held here."""

    __tablename__ = "principal"
    __table_args__ = (Index("ix_principal_tenant_id", "tenant_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    kind: Mapped[str] = mapped_column(String(20))
    # Subject at the identity provider, once one is connected (Phase 6).
    external_id: Mapped[str | None] = mapped_column(String(200), default=None)
    display_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RoleBinding(Base):
    __tablename__ = "role_binding"
    __table_args__ = (UniqueConstraint("principal_id", "role", "scope_type", "scope_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    principal_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("principal.id"))
    role: Mapped[str] = mapped_column(String(20))
    scope_type: Mapped[str] = mapped_column(String(20))
    # The tenant, team or project the role holds in; no foreign key, since the target
    # table depends on ``scope_type``.
    scope_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ApiKey(Base):
    """An issued key. The key itself is never stored (ADR-0028)."""

    __tablename__ = "api_key"
    __table_args__ = (Index("ix_api_key_tenant_id", "tenant_id"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("project.id"))
    principal_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("principal.id"))
    # Ties traffic to an inventory entry. The table belongs to the compliance toolkit
    # and is named here by string: the gateway does not import it.
    ai_system_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_system.id"), default=None
    )
    name: Mapped[str] = mapped_column(String(200))
    key_id: Mapped[str] = mapped_column(String(32), unique=True)
    key_hash: Mapped[str] = mapped_column(String(64))
    pepper_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
