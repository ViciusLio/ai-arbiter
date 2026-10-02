"""Schema migrations, run programmatically so that the CLI needs no ``alembic.ini``.

The migration scripts ship inside the package (``ai_arbiter/migrations``); ``alembic.ini``
at the repository root exists only for developers who generate new revisions.
"""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection

import ai_arbiter
from ai_arbiter.core.persistence.database import Database, ensure_sqlite_directory

# Located by path, not imported: the migration environment imports the models of every
# package, which the shared kernel must not depend on.
MIGRATIONS_PATH = Path(ai_arbiter.__file__).parent / "migrations"


def alembic_config(database_url: str | None = None) -> Config:
    config = Config()
    # Option values go through ConfigParser interpolation, where "%" is special.
    config.set_main_option("script_location", str(MIGRATIONS_PATH).replace("%", "%%"))
    config.set_main_option("path_separator", "os")
    if database_url is not None:
        config.attributes["database_url"] = database_url
    return config


def upgrade(database_url: str, revision: str = "head") -> None:
    """Apply migrations up to ``revision``. Must not be called from a running event loop."""
    ensure_sqlite_directory(database_url)
    command.upgrade(alembic_config(database_url), revision)


def downgrade(database_url: str, revision: str) -> None:
    """Revert migrations down to ``revision``. Must not be called from a running event loop."""
    command.downgrade(alembic_config(database_url), revision)


async def upgrade_async(database_url: str, revision: str = "head") -> None:
    await asyncio.to_thread(upgrade, database_url, revision)


async def downgrade_async(database_url: str, revision: str) -> None:
    await asyncio.to_thread(downgrade, database_url, revision)


def head_revision() -> str | None:
    """The newest revision known to this version of the package."""
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def _current(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


async def current_revision(database: Database) -> str | None:
    """The revision the database is at, or ``None`` if it was never migrated."""
    async with database.engine.connect() as connection:
        return await connection.run_sync(_current)
