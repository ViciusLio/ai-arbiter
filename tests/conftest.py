"""Shared fixtures.

Database tests run on SQLite always, and on PostgreSQL as well when
``ARBITER_TEST_DATABASE_URL`` points to an empty database (CI does this).
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from ai_arbiter.core.persistence import migrate
from ai_arbiter.core.persistence.database import Database

TEST_DATABASE_ENV = "ARBITER_TEST_DATABASE_URL"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep the developer's own configuration out of the tests.

    Settings read ``ARBITER_*`` variables and ``./arbiter.yaml``; tests run in an empty
    directory with those variables removed.
    """
    for name in list(os.environ):
        if name.startswith("ARBITER_") and name != TEST_DATABASE_ENV:
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)


def sqlite_url(directory: Path, name: str = "test.db") -> str:
    return f"sqlite+aiosqlite:///{(directory / name).as_posix()}"


@pytest.fixture(params=["sqlite", "postgresql"])
def database_url(request: pytest.FixtureRequest, tmp_path: Path) -> str:
    if request.param == "postgresql":
        url = os.environ.get(TEST_DATABASE_ENV)
        if not url:
            pytest.skip(f"set {TEST_DATABASE_ENV} to run on PostgreSQL")
        # The driver is part of the gateway extra. An environment without extras skips
        # these tests even when a database is available, as in the dev container.
        pytest.importorskip("asyncpg", reason="PostgreSQL tests need the gateway extra")
        return url
    return sqlite_url(tmp_path)


@pytest.fixture
async def migrated_url(database_url: str) -> AsyncIterator[str]:
    await migrate.upgrade_async(database_url)
    yield database_url
    await migrate.downgrade_async(database_url, "base")


@pytest.fixture
async def database(migrated_url: str) -> AsyncIterator[Database]:
    instance = Database(migrated_url)
    yield instance
    await instance.dispose()
