from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.persistence import migrate
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.migrations.metadata import target_metadata


def _differences(connection: Connection) -> list[Any]:
    return list(compare_metadata(MigrationContext.configure(connection), target_metadata))


def _tables(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


def _newest_revision_file() -> str:
    return max(
        path.name.split("_")[0] for path in (migrate.MIGRATIONS_PATH / "versions").glob("*.py")
    )


async def test_upgrade_brings_the_database_to_head(database: Database) -> None:
    assert migrate.head_revision() == _newest_revision_file()
    assert await migrate.current_revision(database) == migrate.head_revision()


async def test_migrated_schema_matches_the_models(database: Database) -> None:
    """A model change without a migration, or the reverse, fails here."""
    async with database.engine.connect() as connection:
        differences = await connection.run_sync(_differences)

    assert differences == []


async def test_unmigrated_database_has_no_revision(database_url: str) -> None:
    database = Database(database_url)
    try:
        assert await migrate.current_revision(database) is None
    finally:
        await database.dispose()


async def test_downgrade_removes_every_table(database_url: str) -> None:
    await migrate.upgrade_async(database_url)
    await migrate.downgrade_async(database_url, "base")

    database = Database(database_url)
    try:
        async with database.engine.connect() as connection:
            tables = await connection.run_sync(_tables)
    finally:
        await database.dispose()

    assert tables <= {"alembic_version"}


async def test_the_project_of_a_system_moves_to_the_list_of_projects_and_back(
    database_url: str,
) -> None:
    """Revision 0011 keeps what a system named before it (ADR-0059)."""
    tenant = sa.table(
        "tenant",
        *(sa.column(name, kind) for name, kind in (("id", sa.Uuid()), ("slug", sa.String()))),
        sa.column("name", sa.String()),
        sa.column("settings", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    old = sa.table(
        "ai_system",
        *(sa.column(name, sa.Uuid()) for name in ("id", "tenant_id", "project_id")),
        *(sa.column(name, sa.String()) for name in ("key", "name", "purpose", "origin")),
        sa.column("lifecycle", sa.String()),
        *(sa.column(name, sa.JSON()) for name in ("attributes", "models_used")),
        *(sa.column(name, sa.DateTime(timezone=True)) for name in ("declared_at", "updated_at")),
    )
    link = sa.table(
        "ai_system_project",
        sa.column("ai_system_id", sa.Uuid()),
        sa.column("project_id", sa.Uuid()),
    )
    tenant_id, named, unnamed, project = new_id(), new_id(), new_id(), new_id()
    now = utcnow()

    def system(identifier: UUID, key: str, project_id: UUID | None) -> dict[str, Any]:
        return {
            "id": identifier, "tenant_id": tenant_id, "project_id": project_id, "key": key,
            "name": key, "purpose": "", "origin": "declared", "lifecycle": "production",
            "attributes": {}, "models_used": [], "declared_at": now, "updated_at": now,
        }  # fmt: skip

    await migrate.upgrade_async(database_url, "0010")
    database = Database(database_url)
    try:
        async with database.engine.begin() as connection:
            await connection.execute(
                sa.insert(tenant).values(
                    id=tenant_id, slug="acme", name="Acme", settings={}, created_at=now
                )
            )
            await connection.execute(
                sa.insert(old), [system(named, "one", project), system(unnamed, "two", None)]
            )
        await database.dispose()

        await migrate.upgrade_async(database_url)
        async with database.engine.connect() as connection:
            moved = (await connection.execute(sa.select(link))).all()
        await database.dispose()

        await migrate.downgrade_async(database_url, "0010")
        async with database.engine.connect() as connection:
            back = (
                await connection.execute(sa.select(old.c.key, old.c.project_id).order_by(old.c.key))
            ).all()
    finally:
        await database.dispose()
        await migrate.downgrade_async(database_url, "base")

    assert [tuple(row) for row in moved] == [(named, project)]
    assert [tuple(row) for row in back] == [("one", project), ("two", None)]
