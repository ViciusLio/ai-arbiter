"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_arbiter import __version__
from ai_arbiter.core.config.settings import Settings, load_settings
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.telemetry import configure_logging, setup_telemetry
from ai_arbiter.gateway.api import health

DESCRIPTION = """
Arbiter is an AI governance gateway and EU AI Act compliance toolkit.

Arbiter is a support tool. It does not provide legal advice.
"""

OPENAPI_TAGS = [
    {"name": "health", "description": "Liveness and readiness of this process."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved.logging)
        telemetry = setup_telemetry(resolved.telemetry, service_version=__version__)
        database = Database(resolved.database.url, echo=resolved.database.echo)
        app.state.settings = resolved
        app.state.database = database
        try:
            yield
        finally:
            await database.dispose()
            telemetry.shutdown()

    app = FastAPI(
        title="Arbiter",
        summary="AI governance gateway and EU AI Act compliance toolkit",
        description=DESCRIPTION,
        version=__version__,
        license_info={"name": "Apache-2.0", "identifier": "Apache-2.0"},
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.include_router(health.router)
    return app
