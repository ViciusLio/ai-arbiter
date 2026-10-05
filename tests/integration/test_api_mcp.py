"""The control plane of the MCP catalogue over HTTP."""

from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")

from sqlalchemy import select

from ai_arbiter.core.audit import AuditEntry
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.persistence.database import Database
from tests.api_support import app_for, issue_key, running
from tests.integration.test_api_compliance import declare, url_of

pytestmark = pytest.mark.usefixtures("gateway_secrets")

SERVER = {"key": "files", "name": "File tools", "url": "https://tools.example.org/mcp"}


async def test_a_server_and_its_grants_are_managed_by_an_admin_and_read_by_an_auditor(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        auditor = await issue_key(app, tenant_id, AccessRole.AUDITOR)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await declare(client, admin, "cv-screening")

        created = await client.post(
            "/api/v1/mcp/servers",
            json={**SERVER, "ai_system": "cv-screening", "credential": "secret://files-token"},
            headers=admin.auth,
        )
        again = await client.post("/api/v1/mcp/servers", json=SERVER, headers=admin.auth)
        grant = await client.post(
            "/api/v1/mcp/servers/files/grants",
            json={"scope_type": "project", "scope_id": str(admin.project_id), "tool": "read"},
            headers=admin.auth,
        )
        listed = await client.get("/api/v1/mcp/servers", headers=auditor.auth)
        fetched = await client.get("/api/v1/mcp/servers/files", headers=auditor.auth)
        grants = await client.get("/api/v1/mcp/grants", headers=auditor.auth)
        codes = [
            (
                await client.post("/api/v1/mcp/servers", json=SERVER, headers=auditor.auth)
            ).status_code,
            (await client.get("/api/v1/mcp/servers", headers=developer.auth)).status_code,
            (await client.delete("/api/v1/mcp/servers/files", headers=auditor.auth)).status_code,
        ]
        revoked = await client.delete(
            f"/api/v1/mcp/grants/{grant.json()['id']}", headers=admin.auth
        )
        removed = await client.delete("/api/v1/mcp/servers/files", headers=admin.auth)
        gone = await client.get("/api/v1/mcp/servers/files", headers=admin.auth)

    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["key"], body["governability"], body["has_credential"]) == (
        "files",
        "not_asked",
        True,
    )
    assert body["ai_system_id"] is not None
    assert "credential" not in body
    assert again.status_code == 409
    assert grant.status_code == 201
    assert grant.json()["tool"] == "read"
    assert [item["key"] for item in listed.json()] == ["files"]
    assert fetched.json()["tools"] == []
    assert [item["server"] for item in grants.json()] == ["files"]
    assert codes == [403, 403, 403]
    assert (revoked.status_code, removed.status_code, gone.status_code) == (204, 204, 404)
    async with database.session() as session:
        actions = (
            await session.scalars(
                select(AuditEntry.action).where(AuditEntry.action.startswith("mcp_"))
            )
        ).all()
    assert sorted(actions) == [
        "mcp_grant.created",
        "mcp_grant.revoked",
        "mcp_server.registered",
        "mcp_server.removed",
    ]


async def test_the_catalogue_of_one_tenant_is_invisible_to_another_and_refuses_unsafe_urls(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        mine = await issue_key(app, tenant_id, AccessRole.ADMIN)
        theirs = await issue_key(app, other_tenant_id, AccessRole.ADMIN)
        await client.post("/api/v1/mcp/servers", json=SERVER, headers=mine.auth)

        elsewhere = await client.get("/api/v1/mcp/servers", headers=theirs.auth)
        hidden = await client.get("/api/v1/mcp/servers/files", headers=theirs.auth)
        plain = await client.post(
            "/api/v1/mcp/servers",
            json={"key": "plain", "name": "Plain", "url": "http://tools.example.org/mcp"},
            headers=mine.auth,
        )
        unknown_system = await client.post(
            "/api/v1/mcp/servers",
            json={"key": "owned", "name": "Owned", "url": SERVER["url"], "ai_system": "nope"},
            headers=mine.auth,
        )

    assert elsewhere.json() == []
    assert hidden.status_code == 404
    assert plain.status_code == 409
    assert "https" in plain.json()["detail"]
    assert unknown_system.status_code == 404
