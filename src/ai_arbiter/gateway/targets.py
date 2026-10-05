"""The catalogues of the gateway as the compliance toolkit reads them."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.invocation import InvocationProtocol
from ai_arbiter.core.targets import GovernedTarget
from ai_arbiter.gateway.a2a.model import A2aAgent
from ai_arbiter.gateway.a2a.registry import governability as agent_governability
from ai_arbiter.gateway.mcp.catalogue import governability as server_governability
from ai_arbiter.gateway.mcp.model import McpServer


class CatalogueTargetDirectory:
    """The ``TargetDirectory`` port, over the MCP catalogue and the A2A registry."""

    def __init__(self, settings: Settings) -> None:
        self._a2a_http_hosts = settings.a2a.allow_http_hosts

    async def targets(self, session: AsyncSession, tenant_id: UUID) -> Sequence[GovernedTarget]:
        servers = await session.scalars(
            select(McpServer).where(McpServer.tenant_id == tenant_id).order_by(McpServer.key)
        )
        agents = await session.scalars(
            select(A2aAgent).where(A2aAgent.tenant_id == tenant_id).order_by(A2aAgent.key)
        )
        found = [
            GovernedTarget(
                protocol=InvocationProtocol.MCP.value,
                key=server.key,
                ai_system_id=server.ai_system_id,
                governability=server_governability(server),
            )
            for server in servers
        ]
        found += [
            GovernedTarget(
                protocol=InvocationProtocol.A2A.value,
                key=agent.key,
                ai_system_id=agent.ai_system_id,
                governability=agent_governability(agent, self._a2a_http_hosts),
                verification=agent.verification,
            )
            for agent in agents
        ]
        return found
