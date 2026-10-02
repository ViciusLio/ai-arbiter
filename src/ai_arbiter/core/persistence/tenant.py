"""Tenant: the root of every tenant-owned row (ADR-0015)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, String, Uuid, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(63), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


async def ensure_tenant(session: AsyncSession, *, slug: str, name: str) -> Tenant:
    """Return the tenant with this slug, creating it if it does not exist."""
    existing = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    if existing is not None:
        return existing
    tenant = Tenant(slug=slug, name=name)
    session.add(tenant)
    await session.flush()
    return tenant
