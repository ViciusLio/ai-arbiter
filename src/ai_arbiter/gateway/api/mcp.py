"""Control plane of the MCP catalogue: servers, what they offer, and the allowlist."""

from collections.abc import Mapping
from datetime import datetime
from functools import partial
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.i18n import Translator, negotiate
from ai_arbiter.gateway.api.compliance import Compliance
from ai_arbiter.gateway.api.deps import Admin, Caller, Reader, Runtime
from ai_arbiter.gateway.api.relay import relay
from ai_arbiter.gateway.identity.model import ScopeType
from ai_arbiter.gateway.identity.service import AuthenticatedKey
from ai_arbiter.gateway.mcp.catalogue import governability
from ai_arbiter.gateway.mcp.model import ANY_TOOL, McpGrant, McpServer, McpTransport
from ai_arbiter.gateway.mcp.protocol import (
    DENIED,
    UPSTREAM_FAILED,
    ProtocolError,
    error_body,
    parse_request,
)
from ai_arbiter.gateway.mcp.proxy import UpstreamUnavailableError
from ai_arbiter.gateway.runtime import GatewayRuntime

admin_router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


class ServerIn(BaseModel):
    key: str
    name: str
    transport: McpTransport = McpTransport.STREAMABLE_HTTP
    url: str | None = None
    # Key of the declared AI system the server belongs to.
    ai_system: str | None = None
    # A secret reference (secret://NAME) for the credential sent upstream.
    credential: str | None = None


class ServerOut(BaseModel):
    key: str
    name: str
    transport: str
    url: str | None
    ai_system_id: UUID | None
    has_credential: bool
    enabled: bool
    # Whether the proxy can stand in front of it: governable, not_asked, legacy_only,
    # not_proxied or disabled.
    governability: str
    protocol_versions: list[str]
    tools: list[str]
    discovered_at: datetime | None


class GrantIn(BaseModel):
    scope_type: Literal["tenant", "project", "ai_system"] = "tenant"
    scope_id: UUID | None = None
    tool: str = Field(default=ANY_TOOL, description="A tool name, or * for every tool.")


class GrantOut(BaseModel):
    id: UUID
    server: str
    scope_type: str
    scope_id: UUID
    tool: str


async def _audit(
    runtime: GatewayRuntime,
    session: AsyncSession,
    caller: AuthenticatedKey,
    action: str,
    resource_type: str,
    resource_id: object,
) -> None:
    await runtime.audit.append(
        session,
        caller.context.tenant_id,
        AuditRecord(
            action=action,
            outcome="ok",
            actor_id=caller.context.principal_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
        ),
    )


async def _server(runtime: GatewayRuntime, session: AsyncSession, server: McpServer) -> ServerOut:
    return ServerOut(
        key=server.key,
        name=server.name,
        transport=server.transport,
        url=server.url,
        ai_system_id=server.ai_system_id,
        has_credential=server.credential is not None,
        enabled=server.enabled,
        governability=governability(server),
        protocol_versions=[str(version) for version in server.protocol_versions],
        tools=list(await runtime.mcp.tools(session, server)),
        discovered_at=server.discovered_at,
    )


def _grant(grant: McpGrant, server_key: str) -> GrantOut:
    return GrantOut(
        id=grant.id,
        server=server_key,
        scope_type=grant.scope_type,
        scope_id=grant.scope_id,
        tool=grant.tool,
    )


@admin_router.get("/servers", summary="List the MCP servers of the catalogue")
async def list_servers(runtime: Runtime, caller: Reader) -> list[ServerOut]:
    async with runtime.database.session() as session:
        return [
            await _server(runtime, session, server)
            for server in await runtime.mcp.list(session, caller.context.tenant_id)
        ]


@admin_router.post(
    "/servers",
    summary="Register an MCP server",
    description="A Streamable HTTP server needs an https URL. A stdio server is only "
    "declared: the proxy never starts a process. Nobody may call a server until a grant "
    "says so.",
    status_code=status.HTTP_201_CREATED,
)
async def register_server(
    body: ServerIn, runtime: Runtime, compliance: Compliance, caller: Admin
) -> ServerOut:
    tenant_id = caller.context.tenant_id
    async with runtime.database.transaction() as session:
        system_id = None
        if body.ai_system is not None:
            system_id = (await compliance.inventory.get(session, tenant_id, body.ai_system)).id
        server = await runtime.mcp.register(
            session,
            tenant_id,
            key=body.key,
            name=body.name,
            transport=body.transport,
            url=body.url,
            ai_system_id=system_id,
            credential=body.credential,
        )
        await _audit(runtime, session, caller, "mcp_server.registered", "mcp_server", server.id)
        return await _server(runtime, session, server)


@admin_router.get("/servers/{key}", summary="An MCP server with the tools it listed")
async def get_server(key: str, runtime: Runtime, caller: Reader) -> ServerOut:
    async with runtime.database.session() as session:
        server = await runtime.mcp.get(session, caller.context.tenant_id, key)
        return await _server(runtime, session, server)


@admin_router.delete(
    "/servers/{key}",
    summary="Remove an MCP server with its tools and grants",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_server(key: str, runtime: Runtime, caller: Admin) -> Response:
    async with runtime.database.transaction() as session:
        server = await runtime.mcp.remove(session, caller.context.tenant_id, key)
        await _audit(runtime, session, caller, "mcp_server.removed", "mcp_server", server.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/servers/{key}/grants",
    summary="Allow the tenant, a project or an AI system to call a server",
    status_code=status.HTTP_201_CREATED,
)
async def create_grant(key: str, body: GrantIn, runtime: Runtime, caller: Admin) -> GrantOut:
    async with runtime.database.transaction() as session:
        grant = await runtime.mcp.grant(
            session,
            caller.context.tenant_id,
            key,
            scope_type=ScopeType(body.scope_type),
            scope_id=body.scope_id,
            tool=body.tool,
        )
        await _audit(runtime, session, caller, "mcp_grant.created", "mcp_grant", grant.id)
    return _grant(grant, key)


@admin_router.get("/grants", summary="List the grants of the catalogue")
async def list_grants(runtime: Runtime, caller: Reader) -> list[GrantOut]:
    async with runtime.database.session() as session:
        return [
            _grant(grant, key)
            for grant, key in await runtime.mcp.grants(session, caller.context.tenant_id)
        ]


@admin_router.delete(
    "/grants/{grant_id}", summary="Withdraw a grant", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_grant(grant_id: UUID, runtime: Runtime, caller: Admin) -> Response:
    async with runtime.database.transaction() as session:
        grant = await runtime.mcp.revoke(session, caller.context.tenant_id, grant_id)
        await _audit(runtime, session, caller, "mcp_grant.revoked", "mcp_grant", grant.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/servers/{key}/discovery",
    summary="Ask a server which revisions it speaks and which tools it lists",
    description="The proxy calls `server/discover` and `tools/list` on the server and stores "
    "the revisions and the names of the tools. A server that does not answer as revision "
    "`2026-07-28` does is recorded as legacy and cannot be governed.",
)
async def discover_server(key: str, runtime: Runtime, caller: Admin) -> ServerOut:
    server = await runtime.mcp_proxy.discover(
        caller.context.tenant_id, key, actor_id=caller.context.principal_id
    )
    async with runtime.database.session() as session:
        return await _server(runtime, session, server)


# --- data plane --------------------------------------------------------------------------

proxy_router = APIRouter(tags=["mcp"])


def _rpc_error(
    status_code: int,
    code: int,
    message: str,
    *,
    request_id: int | str | None = None,
    data: Mapping[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        error_body(code, message, request_id=request_id, data=data), status_code=status_code
    )


@proxy_router.post(
    "/mcp/{server_key}",
    summary="Call an MCP server of the catalogue through the proxy",
    description="The MCP endpoint of a server, as the Streamable HTTP transport of revision "
    "`2026-07-28` defines it. Authenticate with an Arbiter API key; the server receives the "
    "credential of the catalogue, never the caller's. A call is forwarded only if a grant "
    "allows it, and every call is written to the audit log without its arguments.",
    response_model=None,
)
async def call_mcp_server(
    server_key: str, request: Request, runtime: Runtime, caller: Caller
) -> Response:
    settings = runtime.settings.mcp
    proxy = runtime.mcp_proxy
    # A browser page on another origin must not drive the proxy with a user's key.
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins:
        return _rpc_error(status.HTTP_403_FORBIDDEN, DENIED, "this origin is not allowed")
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > settings.max_request_bytes:
        return _rpc_error(status.HTTP_413_CONTENT_TOO_LARGE, DENIED, "the request is too large")
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > settings.max_request_bytes:
            return _rpc_error(status.HTTP_413_CONTENT_TOO_LARGE, DENIED, "the request is too large")
    headers = {name.lower(): value for name, value in request.headers.items()}
    try:
        parsed = parse_request(body, headers)
    except ProtocolError as error:
        return _rpc_error(
            error.status, error.code, str(error), request_id=error.request_id, data=error.data
        )

    prepared = await proxy.authorize(caller, server_key, parsed, len(body))
    if not prepared.allowed:
        rules = [match.rule_id for match in prepared.decision.matches]
        unknown = "MCP-SERVER-UNKNOWN" in rules
        translator = Translator(negotiate(request.headers.get("accept-language")))
        return _rpc_error(
            status.HTTP_404_NOT_FOUND if unknown else status.HTTP_403_FORBIDDEN,
            DENIED,
            translator.text(prepared.decision.matches[0].message_key),
            request_id=parsed.request_id,
            data={"rules": rules, "decision_id": str(prepared.decision.id)},
        )

    try:
        upstream = await proxy.forward(prepared, body, headers)
    except UpstreamUnavailableError as error:
        await proxy.complete(
            prepared, status_code=None, response_bytes=None, streamed=False, reason=error.reason
        )
        return _rpc_error(
            status.HTTP_502_BAD_GATEWAY, UPSTREAM_FAILED, str(error), request_id=parsed.request_id
        )

    return await relay(
        upstream,
        max_bytes=settings.max_response_bytes,
        complete=partial(proxy.complete, prepared),
        failure=lambda: _rpc_error(
            status.HTTP_502_BAD_GATEWAY,
            UPSTREAM_FAILED,
            "the answer of the MCP server could not be relayed",
            request_id=parsed.request_id,
        ),
    )
