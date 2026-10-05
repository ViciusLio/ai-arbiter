"""Application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from ai_arbiter import __version__
from ai_arbiter.compliance.runtime import ComplianceRuntime, build_compliance
from ai_arbiter.core.config.settings import Role, Settings, load_settings
from ai_arbiter.core.domain.time import Clock
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.ports import AuditLog, EventBus, SystemDirectory
from ai_arbiter.core.telemetry import configure_logging, setup_telemetry
from ai_arbiter.gateway.api import a2a, admin, chat, compliance, errors, health, mcp
from ai_arbiter.gateway.runtime import build_runtime

DESCRIPTION = """
Arbiter is an AI governance gateway and EU AI Act compliance toolkit.

**Data plane** (`/v1`): an OpenAI-compatible endpoint. Every request is authenticated,
checked by policy, routed, metered and written to a hash-chained audit log. Prompt and
completion text is not stored.

**Control plane** (`/api/v1`): identity, budgets, usage and the audit log; the inventory
of AI systems with their indicative classification under the EU AI Act, findings and the
daily digest. Classifications and findings are indicative until a person reviews them.

Authenticate with `Authorization: Bearer <API key>`. Errors follow RFC 9457 (problem
details) and include the decision that caused them, where there is one.

Arbiter is a support tool. It does not provide legal advice.
"""

OPENAPI_TAGS = [
    {"name": "models", "description": "OpenAI-compatible data plane."},
    {"name": "identity", "description": "Teams, projects, principals, roles and API keys."},
    {"name": "finops", "description": "Budgets, usage and estimated cost."},
    {"name": "audit", "description": "The hash-chained audit log: read, verify, export."},
    {
        "name": "inventory",
        "description": "Declared AI systems and their indicative AI Act classification.",
    },
    {"name": "findings", "description": "Scans, findings and their review, suppressions."},
    {"name": "digest", "description": "The daily digest."},
    {"name": "reports", "description": "The system report and the audit report."},
    {
        "name": "mcp",
        "description": "The catalogue of MCP servers, their tools and who may call them.",
    },
    {
        "name": "a2a",
        "description": "The registry of A2A agents, what their card says and who may call them.",
    },
    {"name": "health", "description": "Liveness and readiness of this process."},
]


def create_app(
    settings: Settings | None = None,
    *,
    provider_options: dict[str, dict[str, Any]] | None = None,
    clock: Clock | None = None,
    mcp_transport: Any = None,
    a2a_transport: Any = None,
) -> FastAPI:
    """Build the application.

    ``provider_options``, ``clock``, ``mcp_transport`` and ``a2a_transport`` exist for
    tests: extra constructor arguments per provider plugin, the clock every service
    reads, and the HTTP transports the MCP proxy and the A2A registry go out through.
    """
    resolved = settings if settings is not None else load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(resolved.logging)
        telemetry = setup_telemetry(resolved.telemetry, service_version=__version__)
        database = Database(resolved.database.url, echo=resolved.database.echo)
        toolkit: list[ComplianceRuntime] = []

        def systems(audit: AuditLog, bus: EventBus, used_clock: Clock) -> SystemDirectory:
            # The compliance toolkit shares the audit log and the event bus of the
            # gateway, and gives it the directory of classified systems.
            toolkit.append(build_compliance(resolved, audit=audit, bus=bus, clock=used_clock))
            return toolkit[0].directory

        try:
            runtime = await build_runtime(
                resolved,
                database,
                provider_options=provider_options,
                clock=clock,
                systems=systems,
                mcp_transport=mcp_transport,
                a2a_transport=a2a_transport,
            )
        except BaseException:
            await database.dispose()
            telemetry.shutdown()
            raise
        app.state.settings = resolved
        app.state.database = database
        app.state.runtime = runtime
        app.state.compliance = toolkit[0]
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
    if Role.MCP in resolved.server.roles:
        app.include_router(mcp.proxy_router)
    if Role.ADMIN in resolved.server.roles:
        app.include_router(admin.router)
        app.include_router(compliance.router)
        app.include_router(mcp.admin_router)
        app.include_router(a2a.admin_router)
    return app
