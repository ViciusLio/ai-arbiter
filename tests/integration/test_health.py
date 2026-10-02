import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")

from ai_arbiter import __version__
from ai_arbiter.core.config import Settings, load_settings
from ai_arbiter.gateway.api.app import create_app
from tests.api_support import running


def settings_for(url: str) -> Settings:
    return load_settings(database={"url": url})


async def test_liveness_reports_the_version(migrated_url: str) -> None:
    async with running(create_app(settings_for(migrated_url))) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_ready_when_the_schema_is_at_head(migrated_url: str) -> None:
    async with running(create_app(settings_for(migrated_url))) as client:
        response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


async def test_not_ready_when_migrations_are_pending(database_url: str) -> None:
    async with running(create_app(settings_for(database_url))) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "migration_pending"},
    }


async def test_not_ready_when_the_database_is_unreachable() -> None:
    pytest.importorskip("asyncpg")
    # Port 9 (discard) on localhost: nothing listens there.
    url = "postgresql+asyncpg://arbiter@127.0.0.1:9/arbiter"

    async with running(create_app(settings_for(url))) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "unavailable"}


async def test_openapi_document_describes_the_service(migrated_url: str) -> None:
    async with running(create_app(settings_for(migrated_url))) as client:
        document = (await client.get("/openapi.json")).json()

    assert document["info"]["title"] == "Arbiter"
    assert document["info"]["version"] == __version__
    assert "not provide legal advice" in document["info"]["description"]
    assert {"/healthz", "/readyz"} <= set(document["paths"])
