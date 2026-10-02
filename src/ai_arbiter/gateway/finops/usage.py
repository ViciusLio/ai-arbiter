"""Assemble a usage report for a tenant: totals from the roll-ups, names from identity."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.gateway.finops.metering import usage_by_scope
from ai_arbiter.gateway.finops.report import UsageReport
from ai_arbiter.gateway.identity.model import Project, ScopeType, Team


async def usage_report(
    session: AsyncSession,
    tenant: Tenant,
    scope_type: ScopeType,
    *,
    start: date,
    end: date,
    generated_at: datetime,
) -> UsageReport:
    """Usage per scope between two days, inclusive.

    Teams and projects are shown by name. Principals and AI systems are shown by
    identifier: a principal's name is personal data and does not belong in a report
    that gets passed around.
    """
    lines = await usage_by_scope(session, tenant.id, scope_type, start=start, end=end)
    names: dict[UUID, str] = {tenant.id: tenant.name}
    if scope_type is ScopeType.TEAM:
        rows = await session.execute(select(Team.id, Team.name).where(Team.tenant_id == tenant.id))
        names.update({row.id: row.name for row in rows})
    elif scope_type is ScopeType.PROJECT:
        rows = await session.execute(
            select(Project.id, Project.name).where(Project.tenant_id == tenant.id)
        )
        names.update({row.id: row.name for row in rows})
    return UsageReport(
        tenant_name=tenant.name,
        scope_type=scope_type.value,
        start=start,
        end=end,
        generated_at=generated_at,
        lines=lines,
        names=names,
    )
