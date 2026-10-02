"""In-process event bus.

``publish`` only writes to the outbox, inside the caller's transaction. Delivery happens
later, in ``dispatch_pending``, so an event is never delivered for a change that was
rolled back and never lost for a change that was committed.

Delivery is at-least-once. If one of several handlers fails, the event is delivered again
to all of them, which is why handlers must be idempotent on the event id.
"""

import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.events.model import Event, OutboxEvent
from ai_arbiter.core.persistence.database import Database

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=Event)


@dataclass(frozen=True)
class DispatchResult:
    delivered: int = 0
    failed: int = 0


class InProcessEventBus:
    def __init__(self, *, max_attempts: int = 5) -> None:
        self._max_attempts = max_attempts
        self._types: dict[str, type[Event]] = {}
        self._handlers: dict[str, list[Callable[[Any], Awaitable[None]]]] = defaultdict(list)

    def subscribe(self, event_type: type[E], handler: Callable[[E], Awaitable[None]]) -> None:
        name = event_type.event_type
        registered = self._types.setdefault(name, event_type)
        if registered is not event_type:
            raise ValueError(f"event type '{name}' is already bound to {registered.__name__}")
        self._handlers[name].append(handler)

    async def publish(self, event: Event, *, session: AsyncSession) -> None:
        session.add(
            OutboxEvent(
                id=event.id,
                tenant_id=event.tenant_id,
                type=event.event_type,
                payload=event.model_dump(mode="json"),
                created_at=event.occurred_at,
            )
        )

    async def dispatch_pending(self, database: Database, *, limit: int = 100) -> DispatchResult:
        """Deliver up to ``limit`` undelivered events, oldest first.

        Handlers run with no transaction of the dispatcher open; the outcome of each
        event is then recorded in its own transaction. Events that failed
        ``max_attempts`` times are left in the outbox and skipped.
        """
        async with database.session() as session:
            pending = (
                await session.scalars(
                    select(OutboxEvent.id)
                    .where(OutboxEvent.dispatched_at.is_(None))
                    .where(OutboxEvent.attempts < self._max_attempts)
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                    .limit(limit)
                )
            ).all()

        delivered = failed = 0
        for event_id in pending:
            # No transaction is open while handlers run: a handler opens its own, and on
            # SQLite, which has one writer, a transaction held here would block it.
            async with database.session() as session:
                row = await session.get(OutboxEvent, event_id)
            # The session is closed here, and with it the transaction a read opens.
            if row is None or row.dispatched_at is not None:
                continue
            error = await self._deliver(row)
            async with database.transaction() as session:
                # Two workers may both have delivered the event: delivery is at least
                # once, which is why handlers are idempotent.
                row = await session.get(
                    OutboxEvent, event_id, with_for_update={"skip_locked": True}
                )
                if row is None or row.dispatched_at is not None:
                    continue
                if error is None:
                    row.dispatched_at = utcnow()
                    delivered += 1
                else:
                    row.attempts += 1
                    row.last_error = error
                    failed += 1
        return DispatchResult(delivered=delivered, failed=failed)

    async def _deliver(self, row: OutboxEvent) -> str | None:
        """Call every handler. Return ``None`` on success, else the error class name."""
        event_class = self._types.get(row.type)
        if event_class is None:
            # Nobody in this process subscribes to this type: nothing to deliver.
            return None
        event = event_class.model_validate(row.payload)
        for handler in self._handlers[row.type]:
            try:
                await handler(event)
            except Exception as exc:
                logger.warning(
                    "event handler failed",
                    extra={"event_id": str(row.id), "event_type": row.type},
                    exc_info=exc,
                )
                return type(exc).__name__
        return None
