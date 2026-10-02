"""Retention: delete what is past its period (ADR-0038)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.classifier.service import ClassifierService
from ai_arbiter.compliance.inventory.model import AISystem
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.config.settings import RetentionSettings
from ai_arbiter.core.domain.risk import RiskTier
from ai_arbiter.core.events.model import OutboxEvent
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.core.ports import AuditLog

# Article 26(6): deployers of high-risk systems keep logs for at least six months.
HIGH_RISK_FLOOR_MONTHS = 6


@dataclass(frozen=True)
class PurgeReport:
    dry_run: bool
    interaction_months: int
    interaction_cutoff: datetime
    high_risk_cutoff: datetime
    outbox_cutoff: datetime
    high_risk_systems: int
    interactions: int
    outbox_events: int


def months_before(moment: datetime, months: int) -> datetime:
    """The same day and time ``months`` earlier, or the last day of that month."""
    index = moment.year * 12 + (moment.month - 1) - months
    year, month = divmod(index, 12)
    day = moment.day
    while True:
        try:
            return moment.replace(year=year, month=month + 1, day=day)
        except ValueError:
            day -= 1


def interaction_months(tenant: Tenant, settings: RetentionSettings) -> int:
    """The tenant's own period if it set one, else the deployment's."""
    override = (tenant.settings or {}).get("retention", {}).get("interaction_months")
    return override if isinstance(override, int) and override >= 1 else settings.interaction_months


async def purge(
    session: AsyncSession,
    tenant: Tenant,
    *,
    settings: RetentionSettings,
    classifier: ClassifierService,
    audit: AuditLog,
    now: datetime,
    dry_run: bool = False,
    actor_id: UUID | None = None,
) -> PurgeReport:
    """Delete interactions and dispatched outbox events that are past their period.

    Interactions of a system whose effective tier is high-risk are kept for at least six
    months, whatever period is configured. Audit entries and usage roll-ups are never
    purged. The purge writes one audit entry with counts and cut-off dates.
    """
    months = interaction_months(tenant, settings)
    cutoff = months_before(now, months)
    floor = min(cutoff, months_before(now, HIGH_RISK_FLOOR_MONTHS))
    outbox_cutoff = now - timedelta(days=settings.outbox_days)

    high_risk: list[UUID] = []
    for system in await session.scalars(select(AISystem).where(AISystem.tenant_id == tenant.id)):
        current = await classifier.current(session, tenant.id, system.id)
        if current is not None and current.tier is RiskTier.HIGH_RISK:
            high_risk.append(system.id)

    ordinary = Interaction.started_at < cutoff
    if high_risk:
        protected = Interaction.ai_system_id.in_(high_risk)
        ordinary = or_(
            and_(
                Interaction.started_at < cutoff, or_(Interaction.ai_system_id.is_(None), ~protected)
            ),
            and_(Interaction.started_at < floor, protected),
        )
    old_interactions = and_(Interaction.tenant_id == tenant.id, ordinary)
    old_events = and_(
        OutboxEvent.tenant_id == tenant.id,
        OutboxEvent.dispatched_at.is_not(None),
        OutboxEvent.dispatched_at < outbox_cutoff,
    )
    interactions = int(
        await session.scalar(select(func.count()).select_from(Interaction).where(old_interactions))
        or 0
    )
    events = int(
        await session.scalar(select(func.count()).select_from(OutboxEvent).where(old_events)) or 0
    )
    report = PurgeReport(
        dry_run=dry_run,
        interaction_months=months,
        interaction_cutoff=cutoff,
        high_risk_cutoff=floor,
        outbox_cutoff=outbox_cutoff,
        high_risk_systems=len(high_risk),
        interactions=interactions,
        outbox_events=events,
    )
    if dry_run:
        return report
    await session.execute(delete(Interaction).where(old_interactions))
    await session.execute(delete(OutboxEvent).where(old_events))
    await audit.append(
        session,
        tenant.id,
        AuditRecord(
            action="retention.purged",
            outcome=f"interactions:{interactions};outbox_events:{events}",
            actor_id=actor_id,
            resource_type="tenant",
            resource_id=str(tenant.id),
            decision={
                "interaction_months": months,
                "interaction_cutoff": cutoff.isoformat(),
                "high_risk_cutoff": floor.isoformat(),
                "outbox_cutoff": outbox_cutoff.isoformat(),
                "high_risk_systems": len(high_risk),
                "interactions": interactions,
                "outbox_events": events,
            },
        ),
    )
    return report
