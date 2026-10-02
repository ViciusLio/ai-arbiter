from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.events.model import OutboxEvent
from ai_arbiter.core.persistence.database import Database, ensure_sqlite_directory
from ai_arbiter.core.persistence.tenant import Tenant, ensure_tenant


async def test_ping_succeeds_on_a_reachable_database(database: Database) -> None:
    await database.ping()


async def test_ensure_tenant_creates_once_and_then_returns_the_same_row(
    database: Database,
) -> None:
    async with database.transaction() as session:
        created = await ensure_tenant(session, slug="acme", name="Acme")
    async with database.transaction() as session:
        again = await ensure_tenant(session, slug="acme", name="Different name")

    assert again.id == created.id
    assert again.name == "Acme"


async def test_tenant_slug_is_unique(database: Database) -> None:
    async with database.transaction() as session:
        session.add(Tenant(slug="acme", name="Acme"))

    async def add_duplicate() -> None:
        async with database.transaction() as session:
            session.add(Tenant(slug="acme", name="Another Acme"))

    with pytest.raises(IntegrityError):
        await add_duplicate()


async def test_transaction_rolls_back_on_error(database: Database) -> None:
    async def failing_unit_of_work() -> None:
        async with database.transaction() as session:
            session.add(Tenant(slug="acme", name="Acme"))
            await session.flush()
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await failing_unit_of_work()

    async with database.session() as session:
        assert await session.scalar(select(Tenant).where(Tenant.slug == "acme")) is None


async def test_timestamps_round_trip_as_utc(database: Database) -> None:
    rome = timezone(timedelta(hours=2))
    async with database.transaction() as session:
        tenant = Tenant(
            slug="acme", name="Acme", created_at=datetime(2026, 7, 1, 12, 0, tzinfo=rome)
        )
        session.add(tenant)

    async with database.session() as session:
        loaded = await session.get(Tenant, tenant.id)

    assert loaded is not None
    assert loaded.created_at == datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    assert loaded.created_at.utcoffset() == timedelta(0)


async def test_foreign_keys_are_enforced(database: Database) -> None:
    """SQLite ignores foreign keys unless enabled per connection; the engine does that."""

    async def add_event_for_unknown_tenant() -> None:
        async with database.transaction() as session:
            session.add(OutboxEvent(id=new_id(), tenant_id=new_id(), type="x", payload={}))

    with pytest.raises(IntegrityError):
        await add_event_for_unknown_tenant()


def test_sqlite_directory_is_created(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "arbiter.db"

    ensure_sqlite_directory(f"sqlite+aiosqlite:///{target.as_posix()}")

    assert target.parent.is_dir()


@pytest.mark.parametrize(
    "url",
    ["sqlite+aiosqlite:///:memory:", "sqlite+aiosqlite://", "postgresql+asyncpg://u@h/db"],
)
def test_no_directory_is_created_for_urls_without_a_file(url: str, tmp_path: Path) -> None:
    ensure_sqlite_directory(url)

    assert list(tmp_path.iterdir()) == []
