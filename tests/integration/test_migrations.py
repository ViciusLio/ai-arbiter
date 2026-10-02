from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.engine import Connection

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
