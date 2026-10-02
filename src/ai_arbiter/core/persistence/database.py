"""Engine and session management."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_arbiter.core.errors import MissingExtraError


def ensure_sqlite_directory(url: str) -> None:
    """Create the parent directory of a SQLite database file, if the URL names one."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return
    if not parsed.database or parsed.database == ":memory:":
        return
    Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite_connection(dbapi_connection: Any, _record: Any) -> None:
    # The driver must not open transactions on its own: ``_begin_sqlite_immediate`` does.
    dbapi_connection.isolation_level = None
    cursor = dbapi_connection.cursor()
    # SQLite does not enforce foreign keys unless asked, per connection.
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _begin_sqlite_immediate(connection: Connection) -> None:
    """Start every transaction as a write transaction.

    SQLite has no row locks. With its default deferred transactions, two sessions that
    read and then write (the audit chain does exactly that) fail with "database is
    locked" instead of waiting. Taking the write lock at ``BEGIN`` makes them queue.
    """
    connection.exec_driver_sql("BEGIN IMMEDIATE")


def build_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """Create the async engine for ``url``.

    The PostgreSQL driver is an optional dependency (ADR-0010). A PostgreSQL URL on an
    install without it raises ``MissingExtraError`` naming the extra, not an import error.
    """
    try:
        return create_async_engine(url, **kwargs)
    except ImportError as exc:
        if exc.name == "asyncpg":
            raise MissingExtraError("gateway", "PostgreSQL support") from exc
        raise


class Database:
    """Owns the engine. One instance per process."""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        ensure_sqlite_directory(url)
        if make_url(url).get_backend_name() == "sqlite":
            self._engine = build_engine(url, echo=echo, connect_args={"timeout": 30})
            event.listen(self._engine.sync_engine, "connect", _configure_sqlite_connection)
            event.listen(self._engine.sync_engine, "begin", _begin_sqlite_immediate)
        else:
            self._engine = build_engine(url, echo=echo)
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def dialect(self) -> str:
        return self._engine.dialect.name

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """A session with no transaction started; the caller commits."""
        async with self._sessions() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """A session in a transaction: committed on exit, rolled back on error."""
        async with self._sessions() as session, session.begin():
            yield session

    async def ping(self) -> None:
        """Run a trivial query.

        Raises ``SQLAlchemyError`` or ``OSError`` if the database is unreachable; which
        one depends on the driver.
        """
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self._engine.dispose()
