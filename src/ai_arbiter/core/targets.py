"""What the compliance toolkit needs to know of the MCP servers and A2A agents of a tenant.

The catalogues belong to the gateway, which the toolkit does not import. This port is
how the scanner reads them; without a gateway it gets ``NoTargetDirectory``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class GovernedTarget:
    """An MCP server or an A2A agent of a catalogue, as the scanner sees it."""

    protocol: str  # "mcp" or "a2a"
    key: str
    ai_system_id: UUID | None
    # governable, or why not: the vocabulary of each catalogue.
    governability: str
    # For an agent, what the signatures of its card say. Null for an MCP server.
    verification: str | None = None


class TargetDirectory(Protocol):
    async def targets(self, session: AsyncSession, tenant_id: UUID) -> Sequence[GovernedTarget]:
        """Every server and agent of the tenant's catalogues."""
        ...


class NoTargetDirectory:
    """The directory of a toolkit that runs without the gateway's catalogues."""

    async def targets(self, session: AsyncSession, tenant_id: UUID) -> Sequence[GovernedTarget]:
        return ()
