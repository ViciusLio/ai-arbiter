"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from ai_arbiter import __version__
from ai_arbiter.core.config.settings import Role, Settings, load_settings
from ai_arbiter.core.domain.time import Clock
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.telemetry import configure_logging, setup_telemetry
from ai_arbiter.gateway.api import admin, chat, errors, health
from ai_arbiter.gateway.runtime import build_runtime

DESCRIPTION = """
Arbiter is an AI governance gateway and EU AI Act compliance toolkit.

**Data plane** (`/v1`): an OpenAI-compatible endpoint. Every request is authenticated,
checked by policy, routed, metered and written to a hash-chained audit log. Prompt and
completion text is not stored.

**Control plane** (`/api/v1`): identity, budgets, usage and the audit log.

Authenticate with `Authorization: Bearer <API key>`. Errors follow RFC 9457 (problem
details) and include the decision that caused them, where there is one.

Arbiter is a support tool. It does not provide legal advice.
"""

OPENAPI_TAGS = [
    {"name": "models", "description": "OpenAI-compatible data plane."},
    {"name": "identity", "description": "Teams, projects, principals, roles and API keys."},
    {"name": "finops", "description": "Budgets, usage and estimated cost."},
    {"name": "audit", "description": "The hash-chained audit log: read, verify, export."},
    {"name": "health", "description": "Liveness and readiness of this process."},
]


def create_app(
    settings: Settings | None = None,
    *,
    provider_options: dict[str, dict[str, Any]] | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Build the application.

    ``provider_options`` and ``clock`` exist for tests: extra constructor arguments per
    provider plugin, and the clock every service reads.
    """
    resolved = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved.logging)
        telemetry = setup_telemetry(resolved.telemetry, service_version=__version__)
        database = Database(resolved.database.url, echo=resolved.database.echo)
        try:
            runtime = await build_runtime(
                resolved, database, provider_options=provider_options, clock=clock
            )
        except BaseException:
            await database.dispose()
            telemetry.shutdown()
            raise
        app.state.settings = resolved
        app.state.database = database
        app.state.runtime = runtime
        try:
            yield
        finally:
            await runtime.aclose()
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
    errors.install(app)
    app.include_router(health.router)
    # A process serves only the parts its roles name (ADR-0020).
    if Role.GATEWAY in resolved.server.roles:
        app.include_router(chat.router)
    if Role.ADMIN in resolved.server.roles:
        app.include_router(admin.router)
    return app
