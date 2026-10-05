"""Control plane of the MCP catalogue: servers, what they offer, and the allowlist."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.gateway.api.compliance import Compliance
from ai_arbiter.gateway.api.deps import Admin, Reader, Runtime
from ai_arbiter.gateway.identity.model import ScopeType
from ai_arbiter.gateway.identity.service import AuthenticatedKey
from ai_arbiter.gateway.mcp.catalogue import governability
from ai_arbiter.gateway.mcp.model import ANY_TOOL, McpGrant, McpServer, McpTransport
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
