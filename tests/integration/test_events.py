from datetime import UTC, datetime
from typing import ClassVar
from uuid import UUID

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from ai_arbiter.core.events import DispatchResult, Event, InProcessEventBus, OutboxEvent
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import ensure_tenant


class SystemDeclared(Event):
    event_type: ClassVar[str] = "test.system_declared"

    system_id: UUID


class SomethingElse(Event):
    event_type: ClassVar[str] = "test.something_else"


@pytest.fixture
async def tenant_id(database: Database) -> UUID:
    async with database.transaction() as session:
        return (await ensure_tenant(session, slug="acme", name="Acme")).id


async def publish(database: Database, bus: InProcessEventBus, *events: Event) -> None:
    async with database.transaction() as session:
        for event in events:
            await bus.publish(event, session=session)


async def outbox_rows(database: Database) -> list[OutboxEvent]:
    async with database.session() as session:
        return list((await session.scalars(select(OutboxEvent))).all())


def test_event_subclass_must_declare_its_type() -> None:
    with pytest.raises(TypeError, match="must define event_type"):

        class Nameless(Event):
            pass


async def test_published_event_is_delivered_with_its_data(
    database: Database, tenant_id: UUID
) -> None:
    bus = InProcessEventBus()
    received: list[SystemDeclared] = []

    async def handler(event: SystemDeclared) -> None:
        received.append(event)

    bus.subscribe(SystemDeclared, handler)
    event = SystemDeclared(tenant_id=tenant_id, system_id=UUID(int=42))
    await publish(database, bus, event)

    result = await bus.dispatch_pending(database)

    assert result == DispatchResult(delivered=1, failed=0)
    assert received == [event]
    (row,) = await outbox_rows(database)
    assert row.dispatched_at is not None
    assert row.attempts == 0


async def test_event_is_not_delivered_twice(database: Database, tenant_id: UUID) -> None:
    bus = InProcessEventBus()
    calls = 0

    async def handler(_: SystemDeclared) -> None:
        nonlocal calls
        calls += 1

    bus.subscribe(SystemDeclared, handler)
    await publish(database, bus, SystemDeclared(tenant_id=tenant_id, system_id=UUID(int=1)))

    await bus.dispatch_pending(database)
    second = await bus.dispatch_pending(database)

    assert calls == 1
    assert second == DispatchResult()


async def test_event_of_a_rolled_back_transaction_is_never_delivered(
    database: Database, tenant_id: UUID
) -> None:
    bus = InProcessEventBus()

    async def failing_unit_of_work() -> None:
        async with database.transaction() as session:
            await bus.publish(
                SystemDeclared(tenant_id=tenant_id, system_id=UUID(int=1)), session=session
            )
            raise RuntimeError("business change failed")

    with pytest.raises(RuntimeError, match="business change failed"):
        await failing_unit_of_work()

    assert await outbox_rows(database) == []


async def test_events_are_delivered_oldest_first(database: Database, tenant_id: UUID) -> None:
    bus = InProcessEventBus()
    order: list[int] = []

    async def handler(event: SystemDeclared) -> None:
        order.append(event.system_id.int)

    bus.subscribe(SystemDeclared, handler)
    await publish(
        database,
        bus,
        SystemDeclared(
            tenant_id=tenant_id, system_id=UUID(int=2), occurred_at=datetime(2026, 1, 2, tzinfo=UTC)
        ),
        SystemDeclared(
            tenant_id=tenant_id, system_id=UUID(int=1), occurred_at=datetime(2026, 1, 1, tzinfo=UTC)
        ),
    )

    await bus.dispatch_pending(database)

    assert order == [1, 2]


async def test_failed_delivery_is_retried_and_records_only_the_error_class(
    database: Database, tenant_id: UUID
) -> None:
    bus = InProcessEventBus()
    attempts = 0

    async def flaky(_: SystemDeclared) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("message that may contain sensitive content")

    bus.subscribe(SystemDeclared, flaky)
    await publish(database, bus, SystemDeclared(tenant_id=tenant_id, system_id=UUID(int=1)))

    first = await bus.dispatch_pending(database)
    (row,) = await outbox_rows(database)
    assert first == DispatchResult(delivered=0, failed=1)
    assert row.dispatched_at is None
    assert row.attempts == 1
    assert row.last_error == "ConnectionError"

    second = await bus.dispatch_pending(database)
    (row,) = await outbox_rows(database)
    assert second == DispatchResult(delivered=1, failed=0)
    assert row.dispatched_at is not None


async def test_event_is_left_alone_after_the_maximum_number_of_attempts(
    database: Database, tenant_id: UUID
) -> None:
    bus = InProcessEventBus(max_attempts=2)
    calls = 0

    async def always_fails(_: SystemDeclared) -> None:
        nonlocal calls
        calls += 1
        raise ValueError("nope")

    bus.subscribe(SystemDeclared, always_fails)
    await publish(database, bus, SystemDeclared(tenant_id=tenant_id, system_id=UUID(int=1)))

    for _ in range(4):
        await bus.dispatch_pending(database)

    (row,) = await outbox_rows(database)
    assert calls == 2
    assert row.attempts == 2
    assert row.dispatched_at is None


async def test_event_without_subscribers_is_marked_dispatched(
    database: Database, tenant_id: UUID
) -> None:
    bus = InProcessEventBus()
    await publish(database, bus, SomethingElse(tenant_id=tenant_id))

    result = await bus.dispatch_pending(database)

    (row,) = await outbox_rows(database)
    assert result == DispatchResult(delivered=1, failed=0)
    assert row.dispatched_at is not None


async def test_every_subscriber_of_a_type_receives_the_event(
    database: Database, tenant_id: UUID
) -> None:
    bus = InProcessEventBus()
    seen: list[str] = []

    async def first(_: SystemDeclared) -> None:
        seen.append("first")

    async def second(_: SystemDeclared) -> None:
        seen.append("second")

    bus.subscribe(SystemDeclared, first)
    bus.subscribe(SystemDeclared, second)
    await publish(database, bus, SystemDeclared(tenant_id=tenant_id, system_id=UUID(int=1)))

    await bus.dispatch_pending(database)

    assert seen == ["first", "second"]


async def test_dispatch_respects_the_batch_limit(database: Database, tenant_id: UUID) -> None:
    bus = InProcessEventBus()
    await publish(database, bus, *(SomethingElse(tenant_id=tenant_id) for _ in range(3)))

    result = await bus.dispatch_pending(database, limit=2)

    assert result.delivered == 2


def test_two_classes_cannot_share_an_event_type() -> None:
    class Impostor(Event):
        event_type: ClassVar[str] = SystemDeclared.event_type

    async def handler(_: BaseModel) -> None: ...

    bus = InProcessEventBus()
    bus.subscribe(SystemDeclared, handler)

    with pytest.raises(ValueError, match="already bound to SystemDeclared"):
        bus.subscribe(Impostor, handler)
