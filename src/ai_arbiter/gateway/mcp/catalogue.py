"""The MCP catalogue: which servers exist, what they offer, and who may call what."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.errors import ConflictError, NotFoundError
from ai_arbiter.gateway.identity.model import ScopeType
from ai_arbiter.gateway.mcp.model import ANY_TOOL, McpGrant, McpServer, McpTool, McpTransport
from ai_arbiter.gateway.urls import checked_url

# The revision the proxy speaks (ADR-0046). Earlier revisions open with a handshake.
MODERN_REVISION = "2026-07-28"
_KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,99}")
_GRANT_SCOPES = (ScopeType.TENANT, ScopeType.PROJECT, ScopeType.AI_SYSTEM)


class Governability:
    """Whether the proxy can stand in front of a server, and why not."""

    GOVERNABLE = "governable"
    NOT_ASKED = "not_asked"  # its revisions were never read
    LEGACY_ONLY = "legacy_only"  # it offers no revision the proxy speaks
    NOT_PROXIED = "not_proxied"  # stdio: declared, never forwarded to
    DISABLED = "disabled"


def governability(server: McpServer) -> str:
    if server.transport != McpTransport.STREAMABLE_HTTP.value:
        return Governability.NOT_PROXIED
    if not server.enabled:
        return Governability.DISABLED
    if not server.protocol_versions:
        return Governability.NOT_ASKED
    if MODERN_REVISION not in server.protocol_versions:
        return Governability.LEGACY_ONLY
    return Governability.GOVERNABLE


@dataclass(frozen=True)
class Caller:
    """What of a request the allowlist looks at."""

    tenant_id: UUID
    project_id: UUID | None
    ai_system_id: UUID | None


def _granted_to(server: McpServer, caller: Caller) -> tuple[Any, ...]:
    """The conditions that select the grants on ``server`` that reach the caller."""
    scopes = [
        (McpGrant.scope_type == ScopeType.TENANT.value) & (McpGrant.scope_id == caller.tenant_id)
    ]
    if caller.project_id is not None:
        scopes.append(
            (McpGrant.scope_type == ScopeType.PROJECT.value)
            & (McpGrant.scope_id == caller.project_id)
        )
    if caller.ai_system_id is not None:
        scopes.append(
            (McpGrant.scope_type == ScopeType.AI_SYSTEM.value)
            & (McpGrant.scope_id == caller.ai_system_id)
        )
    return (
        McpGrant.tenant_id == caller.tenant_id,
        McpGrant.server_id == server.id,
        or_(*scopes),
    )


class McpCatalogue:
    def __init__(self, *, allow_http_hosts: Sequence[str] = (), clock: Clock | None = None) -> None:
        self._allow_http_hosts = frozenset(host.lower() for host in allow_http_hosts)
        self._clock = clock if clock is not None else SystemClock()

    def _checked_url(self, url: str) -> str:
        return checked_url(
            url,
            what="a server",
            allow_http_hosts=self._allow_http_hosts,
            setting="mcp.allow_http_hosts",
        )

    # Servers

    async def register(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        key: str,
        name: str,
        transport: McpTransport = McpTransport.STREAMABLE_HTTP,
        url: str | None = None,
        ai_system_id: UUID | None = None,
        credential: str | None = None,
    ) -> McpServer:
        if not _KEY.fullmatch(key):
            raise ConflictError(
                "the key of a server uses lower-case letters, digits and hyphens, 100 at most"
            )
        if not name.strip():
            raise ConflictError("a server needs a name")
        if transport is McpTransport.STREAMABLE_HTTP:
            if url is None:
                raise ConflictError("a Streamable HTTP server needs its URL")
            url = self._checked_url(url)
        elif url is not None or credential is not None:
            raise ConflictError(
                "a stdio server is only declared: it has no URL and no credential, and the "
                "proxy never starts it"
            )
        if credential is not None:
            try:
                SecretRef.parse(credential)
            except ValueError as error:
                raise ConflictError(f"credential: {error}") from error
        existing = await session.scalar(
            select(McpServer).where(McpServer.tenant_id == tenant_id, McpServer.key == key)
        )
        if existing is not None:
            raise ConflictError(f"an MCP server with the key '{key}' already exists")
        server = McpServer(
            tenant_id=tenant_id,
            key=key,
            name=name.strip(),
            transport=transport.value,
            url=url,
            ai_system_id=ai_system_id,
            credential=credential,
            created_at=self._clock.now(),
        )
        session.add(server)
        await session.flush()
        return server

    async def list(self, session: AsyncSession, tenant_id: UUID) -> Sequence[McpServer]:
        return (
            await session.scalars(
                select(McpServer).where(McpServer.tenant_id == tenant_id).order_by(McpServer.key)
            )
        ).all()

    async def find(self, session: AsyncSession, tenant_id: UUID, key: str) -> McpServer | None:
        return await session.scalar(
            select(McpServer).where(McpServer.tenant_id == tenant_id, McpServer.key == key)
        )

    async def get(self, session: AsyncSession, tenant_id: UUID, key: str) -> McpServer:
        server = await self.find(session, tenant_id, key)
        if server is None:
            raise NotFoundError(f"no MCP server with the key '{key}'")
        return server

    async def set_enabled(
        self, session: AsyncSession, tenant_id: UUID, key: str, enabled: bool
    ) -> McpServer:
        server = await self.get(session, tenant_id, key)
        server.enabled = enabled
        await session.flush()
        return server

    async def remove(self, session: AsyncSession, tenant_id: UUID, key: str) -> McpServer:
        """Delete a server with its tools and grants. Past calls keep its key."""
        server = await self.get(session, tenant_id, key)
        await session.execute(delete(McpGrant).where(McpGrant.server_id == server.id))
        await session.execute(delete(McpTool).where(McpTool.server_id == server.id))
        await session.delete(server)
        await session.flush()
        return server

    # What a server offers

    async def tools(self, session: AsyncSession, server: McpServer) -> Sequence[str]:
        return (
            await session.scalars(
                select(McpTool.name).where(McpTool.server_id == server.id).order_by(McpTool.name)
            )
        ).all()

    async def record_discovery(
        self,
        session: AsyncSession,
        server: McpServer,
        *,
        protocol_versions: Sequence[str],
        tools: Sequence[str] | None,
    ) -> None:
        """Store what the server said of itself. ``tools`` is ``None`` when it was not asked."""
        now = self._clock.now()
        server.protocol_versions = sorted(set(protocol_versions))
        server.discovered_at = now
        if tools is not None:
            known = set(await self.tools(session, server))
            listed = {name[:200] for name in tools if name}
            if known - listed:
                await session.execute(
                    delete(McpTool).where(
                        McpTool.server_id == server.id, McpTool.name.in_(known - listed)
                    )
                )
            for name in sorted(listed - known):
                session.add(
                    McpTool(tenant_id=server.tenant_id, server_id=server.id, name=name, seen_at=now)
                )
        await session.flush()

    # The allowlist

    async def grant(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        key: str,
        *,
        scope_type: ScopeType,
        scope_id: UUID | None,
        tool: str = ANY_TOOL,
    ) -> McpGrant:
        if scope_type not in _GRANT_SCOPES:
            raise ConflictError("a grant is given to the tenant, a project or an AI system")
        target = tenant_id if scope_type is ScopeType.TENANT else scope_id
        if target is None:
            raise ConflictError(f"a grant to a {scope_type.value} needs its id")
        if not tool or len(tool) > 200:
            raise ConflictError("a grant names one tool, or * for every tool of the server")
        server = await self.get(session, tenant_id, key)
        existing = await session.scalar(
            select(McpGrant).where(
                McpGrant.server_id == server.id,
                McpGrant.scope_type == scope_type.value,
                McpGrant.scope_id == target,
                McpGrant.tool == tool,
            )
        )
        if existing is not None:
            return existing
        grant = McpGrant(
            tenant_id=tenant_id,
            server_id=server.id,
            scope_type=scope_type.value,
            scope_id=target,
            tool=tool,
            created_at=self._clock.now(),
        )
        session.add(grant)
        await session.flush()
        return grant

    async def grants(
        self, session: AsyncSession, tenant_id: UUID, key: str | None = None
    ) -> Sequence[tuple[McpGrant, str]]:
        """Grants with the key of their server, of one server or of the tenant."""
        query = (
            select(McpGrant, McpServer.key)
            .join(McpServer, McpServer.id == McpGrant.server_id)
            .where(McpGrant.tenant_id == tenant_id)
            .order_by(McpServer.key, McpGrant.scope_type, McpGrant.tool, McpGrant.id)
        )
        if key is not None:
            query = query.where(McpServer.key == key)
        return [(grant, server_key) for grant, server_key in await session.execute(query)]

    async def revoke(self, session: AsyncSession, tenant_id: UUID, grant_id: UUID) -> McpGrant:
        grant = await session.scalar(
            select(McpGrant).where(McpGrant.tenant_id == tenant_id, McpGrant.id == grant_id)
        )
        if grant is None:
            raise NotFoundError(f"grant {grant_id} not found")
        await session.delete(grant)
        await session.flush()
        return grant

    async def allows(
        self,
        session: AsyncSession,
        server: McpServer,
        caller: Caller,
        tool: str | None,
        *,
        whole_server: bool = False,
    ) -> bool:
        """Whether the caller may use the server, and ``tool`` when one is named.

        Nothing is allowed until a grant says so. A request that only asks what the
        server offers needs any grant on it. With ``whole_server``, only a grant for
        every tool counts: that is what anything other than listing and calling a tool
        needs, because a grant for one tool says nothing about resources and prompts.
        """
        query = select(McpGrant.id).where(*_granted_to(server, caller))
        if whole_server:
            query = query.where(McpGrant.tool == ANY_TOOL)
        elif tool is not None:
            query = query.where(McpGrant.tool.in_((tool, ANY_TOOL)))
        return await session.scalar(query.limit(1)) is not None

    async def callable_tools(
        self, session: AsyncSession, server: McpServer, caller: Caller
    ) -> frozenset[str] | None:
        """The tools the caller's grants name, or ``None`` when a grant covers every tool."""
        named = (
            await session.scalars(
                select(McpGrant.tool).where(*_granted_to(server, caller)).distinct()
            )
        ).all()
        return None if ANY_TOOL in named else frozenset(named)
