"""Event handlers of the compliance toolkit, run by ``arbiter worker``.

Handlers are idempotent: delivery is at least once (ADR-0016), and classifying a system
whose facts did not change writes nothing.
"""

from uuid import UUID

from ai_arbiter.compliance.inventory.model import SystemChanged, SystemDeclared
from ai_arbiter.compliance.runtime import ComplianceRuntime
from ai_arbiter.core.errors import NotFoundError
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.ports import EventBus


def register_handlers(bus: EventBus, database: Database, compliance: ComplianceRuntime) -> None:
    """Subscribe: a system is classified when it is declared and when it changes."""

    async def classify(tenant_id: UUID, system_id: UUID) -> None:
        async with database.transaction() as session:
            try:
                system = await compliance.inventory.get_by_id(session, tenant_id, system_id)
            except NotFoundError:
                return  # declared and removed before the event was delivered
            await compliance.classifier.classify_system(session, system)

    async def on_declared(event: SystemDeclared) -> None:
        await classify(event.tenant_id, event.ai_system_id)

    async def on_changed(event: SystemChanged) -> None:
        await classify(event.tenant_id, event.ai_system_id)

    bus.subscribe(SystemDeclared, on_declared)
    bus.subscribe(SystemChanged, on_changed)
