"""The MCP proxy between a client and a server of the official SDK (I-40).

Both are the real implementations: the client of ``mcp`` talks to Arbiter, and Arbiter
forwards to a server built with ``mcp``. They are joined in process, with no socket: the
proxy reaches the server through an ASGI transport, and the client reaches Arbiter the
same way. Nothing here is a stand-in written by this project.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")
pytest.importorskip("mcp", reason="needs the MCP SDK of the development dependencies")

import httpx
import httpx2
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import select

from ai_arbiter.core.audit import AuditEntry
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.invocation import Invocation
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.gateway.api.app import create_app
from tests.api_support import Issued, gateway_settings, issue_key
from tests.integration.test_api_compliance import url_of
from tests.support import text_in_database

pytestmark = pytest.mark.usefixtures("gateway_secrets")

SERVER_URL = "https://tools.example.org/mcp"


def build_server() -> MCPServer:
    server = MCPServer("file-tools", version="1.0.0")

    @server.tool()
    def read(path: str) -> str:
        """Read a file."""
        return f"contents of {path}"

    @server.tool()
    def write(path: str, text: str) -> str:
        """Write a file."""
        return f"wrote {len(text)} characters to {path}"

    return server


@asynccontextmanager
async def stack(database: Database) -> AsyncIterator[tuple[Any, httpx.AsyncClient]]:
    """A server of the SDK behind Arbiter, both started, and a client for Arbiter's API."""
    upstream = build_server().streamable_http_app(
        transport_security=TransportSecuritySettings(
            allowed_hosts=["tools.example.org"], allowed_origins=[]
        )
    )
    app = create_app(
        gateway_settings(url_of(database)), mcp_transport=httpx.ASGITransport(app=upstream)
    )
    async with (
        upstream.router.lifespan_context(upstream),
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://arbiter.test"
        ) as admin_client,
    ):
        yield app, admin_client


@asynccontextmanager
async def mcp_client(app: Any, key: Issued, server: str = "files") -> AsyncIterator[Client]:
    """The client of the SDK, pointed at Arbiter's endpoint for a server of the catalogue."""
    async with (
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), headers=key.auth) as http,
        Client(
            streamable_http_client(f"http://arbiter.test/mcp/{server}", http_client=http)
        ) as client,
    ):
        yield client


async def catalogue(client: httpx.AsyncClient, admin: Issued, **grant: Any) -> dict[str, Any]:
    created = await client.post(
        "/api/v1/mcp/servers",
        json={"key": "files", "name": "File tools", "url": SERVER_URL},
        headers=admin.auth,
    )
    assert created.status_code == 201, created.text
    found = await client.post("/api/v1/mcp/servers/files/discovery", headers=admin.auth)
    assert found.status_code == 200, found.text
    given = await client.post(
        "/api/v1/mcp/servers/files/grants",
        json=grant or {"scope_type": "tenant"},
        headers=admin.auth,
    )
    assert given.status_code == 201, given.text
    return dict(found.json())


async def test_discovery_reads_the_revisions_and_the_tools_of_a_real_server(
    database: Database, tenant_id: UUID
) -> None:
    async with stack(database) as (app, admin_client):
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        discovered = await catalogue(admin_client, admin)

    assert discovered["governability"] == "governable"
    assert "2026-07-28" in discovered["protocol_versions"]
    assert discovered["tools"] == ["read", "write"]


async def test_a_real_client_calls_a_tool_of_a_real_server_through_the_proxy(
    database: Database, tenant_id: UUID
) -> None:
    async with stack(database) as (app, admin_client):
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await catalogue(admin_client, admin)
        async with mcp_client(app, developer) as client:
            version = client.protocol_version
            tools = await client.list_tools()
            result = await client.call_tool("read", {"path": "report-of-ada-lovelace.txt"})

    assert version == "2026-07-28"
    assert sorted(tool.name for tool in tools.tools) == ["read", "write"]
    assert not result.is_error
    assert "contents of report-of-ada-lovelace.txt" in str(result.content)
    async with database.session() as session:
        rows = (
            await session.scalars(select(Invocation).order_by(Invocation.started_at, Invocation.id))
        ).all()
        entries = (
            await session.scalars(select(AuditEntry).where(AuditEntry.action == "mcp.call"))
        ).all()
    called = [row for row in rows if row.method == "tools/call"]
    assert [(row.name, row.outcome, row.status_code) for row in called] == [("read", "ok", 200)]
    assert {row.outcome for row in rows} == {"ok"}
    assert len(entries) == len(rows)
    assert await text_in_database(database, "report-of-ada-lovelace") == []


async def test_a_real_client_is_refused_the_tool_its_grant_does_not_name(
    database: Database, tenant_id: UUID
) -> None:
    async with stack(database) as (app, admin_client):
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await catalogue(
            admin_client,
            admin,
            scope_type="project",
            scope_id=str(developer.project_id),
            tool="read",
        )
        async with mcp_client(app, developer) as client:
            shown = await client.list_tools()
            allowed = await client.call_tool("read", {"path": "a.txt"})
            with pytest.raises(Exception, match="No grant allows") as refused:
                await client.call_tool("write", {"path": "a.txt", "text": "secret words"})

    assert [tool.name for tool in shown.tools] == ["read"]
    assert not allowed.is_error
    assert refused.value is not None
    async with database.session() as session:
        denied = (
            await session.scalars(select(Invocation).where(Invocation.outcome == "denied"))
        ).all()
    assert [(row.method, row.name, row.reason) for row in denied] == [
        ("tools/call", "write", "MCP-CALL-NOT-GRANTED")
    ]
    assert await text_in_database(database, "secret words") == []
