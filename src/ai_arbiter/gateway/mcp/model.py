"""MCP catalogue tables: the servers an organisation knows, their tools, who may call them."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.persistence.base import Base
from ai_arbiter.core.persistence.types import UTCDateTime

# In a grant, stands for every tool of the server.
ANY_TOOL = "*"


class McpTransport(StrEnum):
    STREAMABLE_HTTP = "streamable_http"
    # Declared so that it is known; never proxied and never started (ADR-0048).
    STDIO = "stdio"


class McpServer(Base):
    __tablename__ = "mcp_server"
    __table_args__ = (UniqueConstraint("tenant_id", "key"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    # Chosen by the organisation; the proxy serves the server under this name.
    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(200))
    transport: Mapped[str] = mapped_column(String(20))
    # Where the proxy forwards to. Null for a server that is only declared.
    url: Mapped[str | None] = mapped_column(String(2000), default=None)
    # The declared AI system the server belongs to. The table belongs to the compliance
    # toolkit and is named here by string: the gateway does not import it.
    ai_system_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_system.id"), default=None
    )
    # A secret reference (secret://NAME) for the credential sent upstream, never the value.
    credential: Mapped[str | None] = mapped_column(String(200), default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # The protocol revisions the server declared when it was last asked. Empty: never asked.
    protocol_versions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    discovered_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class McpTool(Base):
    """A tool a server listed. Its name only: descriptions and schemas are not kept."""

    __tablename__ = "mcp_tool"
    __table_args__ = (UniqueConstraint("server_id", "name"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    server_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("mcp_server.id"))
    name: Mapped[str] = mapped_column(String(200))
    seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class McpGrant(Base):
    """Permission for a project, an AI system or the whole tenant to call a tool (ADR-0049)."""

    __tablename__ = "mcp_grant"
    __table_args__ = (UniqueConstraint("server_id", "scope_type", "scope_id", "tool"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("tenant.id"))
    server_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("mcp_server.id"))
    scope_type: Mapped[str] = mapped_column(String(20))
    scope_id: Mapped[UUID] = mapped_column(Uuid)
    # A tool name, or ``*`` for every tool of the server.
    tool: Mapped[str] = mapped_column(String(200), default=ANY_TOOL)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
