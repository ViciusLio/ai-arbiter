"""The MCP proxy end to end, against a stand-in server: decide, record, forward."""

import json
from typing import Any
from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")
pytest.importorskip("mcp_types", reason="needs the mcp extra")

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from ai_arbiter.core.audit import AuditEntry
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.invocation import Invocation
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.gateway.api.app import create_app
from tests.api_support import Issued, gateway_settings, issue_key, running
from tests.integration.test_api_compliance import key_for_system, url_of
from tests.mcp_support import MCP_URL, REVISION, FakeMcpServer, mcp_request
from tests.support import text_in_database

pytestmark = pytest.mark.usefixtures("gateway_secrets")

DENIED = -32010
# Not a credential of anything: what the stand-in server expects in these tests.
UPSTREAM_TOKEN = "-".join(["token", "for", "tests"])


def app_with(mcp_server: FakeMcpServer, database: Database, **overrides: Any) -> FastAPI:
    return create_app(
        gateway_settings(url_of(database), **overrides), mcp_transport=mcp_server.transport
    )


async def register(
    client: httpx.AsyncClient,
    admin: Issued,
    *,
    grant: dict[str, Any] | None = None,
    discover: bool = True,
    **server: Any,
) -> None:
    body = {"key": "files", "name": "File tools", "url": MCP_URL, **server}
    created = await client.post("/api/v1/mcp/servers", json=body, headers=admin.auth)
    assert created.status_code == 201, created.text
    if discover:
        found = await client.post("/api/v1/mcp/servers/files/discovery", headers=admin.auth)
        assert found.status_code == 200, found.text
    if grant is not None:
        given = await client.post(
            "/api/v1/mcp/servers/files/grants", json=grant, headers=admin.auth
        )
        assert given.status_code == 201, given.text


async def call(
    client: httpx.AsyncClient,
    key: Issued,
    method: str = "tools/call",
    *,
    server: str = "files",
    name: str | None = "read",
    **options: Any,
) -> httpx.Response:
    named = name if method in ("tools/call", "prompts/get", "resources/read") else None
    extra = options.pop("headers", {})
    body, headers = mcp_request(method, name=named, **options)
    return await client.post(
        f"/mcp/{server}", content=body, headers={**headers, **key.auth, **extra}
    )


async def invocations(database: Database) -> list[Invocation]:
    async with database.session() as session:
        rows = await session.scalars(
            select(Invocation).order_by(Invocation.started_at, Invocation.id)
        )
        return list(rows.all())


async def audit(database: Database, action: str = "mcp.call") -> list[AuditEntry]:
    async with database.session() as session:
        rows = await session.scalars(
            select(AuditEntry).where(AuditEntry.action == action).order_by(AuditEntry.seq)
        )
        return list(rows.all())


async def test_a_granted_call_is_forwarded_with_the_credential_of_the_catalogue_and_recorded(
    database: Database, tenant_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARBITER_SECRET_FILES_TOKEN", UPSTREAM_TOKEN)
    server = FakeMcpServer()
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await register(
            client, admin, grant={"scope_type": "tenant"}, credential="secret://files-token"
        )
        listed = (await client.get("/api/v1/mcp/servers/files", headers=admin.auth)).json()
        body, headers = mcp_request(
            "tools/call", name="read", arguments={"path": "contract-of-ada-lovelace.pdf"}
        )
        response = await client.post(
            "/mcp/files", content=body, headers={**headers, **developer.auth}
        )

    assert (listed["governability"], listed["tools"]) == ("governable", ["read", "write"])
    assert listed["protocol_versions"] == [REVISION]
    assert response.status_code == 200, response.text
    assert response.json()["result"]["content"][0]["text"] == "ran read"
    forwarded = server.requests[-1]
    assert str(forwarded.url) == MCP_URL
    assert forwarded.content == body
    assert forwarded.headers["authorization"] == f"Bearer {UPSTREAM_TOKEN}"
    assert developer.key not in str(forwarded.headers)
    assert (forwarded.headers["mcp-method"], forwarded.headers["mcp-name"]) == (
        "tools/call",
        "read",
    )
    (row,) = await invocations(database)
    assert (row.protocol, row.target, row.target_known) == ("mcp", "files", True)
    assert (row.method, row.name, row.outcome, row.status_code) == ("tools/call", "read", "ok", 200)
    assert (row.project_id, row.principal_id) == (developer.project_id, developer.principal_id)
    assert (row.request_bytes, row.streamed) == (len(body), False)
    assert row.response_bytes
    assert row.duration_ms is not None
    (entry,) = await audit(database)
    assert (entry.outcome, entry.resource_type, entry.resource_id) == (
        "allow",
        "invocation",
        str(row.id),
    )
    assert entry.decision is not None
    assert entry.decision["details"]["method"] == "tools/call"
    # Neither the arguments nor the result are anywhere in the database.
    assert await text_in_database(database, "contract-of-ada-lovelace") == []
    assert await text_in_database(database, "ran read") == []
    assert await text_in_database(database, UPSTREAM_TOKEN) == []


async def test_without_a_grant_nothing_is_forwarded_and_the_refusal_is_audited(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer()
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await register(client, admin)
        before = len(server.requests)
        response = await call(client, developer, headers={"accept-language": "it"})

    assert response.status_code == 403
    error = response.json()["error"]
    assert (error["code"], response.json()["id"]) == (DENIED, 1)
    assert error["data"]["rules"] == ["MCP-CALL-NOT-GRANTED"]
    assert error["message"].startswith("Nessuna autorizzazione")
    assert len(server.requests) == before
    (row,) = await invocations(database)
    assert (row.outcome, row.reason, row.status_code) == ("denied", "MCP-CALL-NOT-GRANTED", None)
    (entry,) = await audit(database)
    assert entry.outcome == "deny"
    assert entry.decision is not None
    assert entry.decision["id"] == error["data"]["decision_id"]


async def test_a_grant_for_one_tool_allows_that_tool_and_listing_and_nothing_else(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer()
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        inside = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        outside = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await register(
            client,
            admin,
            grant={"scope_type": "project", "scope_id": str(inside.project_id), "tool": "read"},
        )
        codes = {
            "read": (await call(client, inside)).status_code,
            "write": (await call(client, inside, name="write")).status_code,
            "list": (await call(client, inside, "tools/list")).status_code,
            "discover": (await call(client, inside, "server/discover")).status_code,
            "resource": (
                await call(client, inside, "resources/read", name="file:///etc/hosts")
            ).status_code,
            "other project": (await call(client, outside)).status_code,
            "other project list": (await call(client, outside, "tools/list")).status_code,
        }

    assert codes == {
        "read": 200,
        "write": 403,
        "list": 200,
        "discover": 200,
        "resource": 403,
        "other project": 403,
        "other project list": 403,
    }
    rows = await invocations(database)
    resource = next(row for row in rows if row.method == "resources/read")
    assert resource.name is None
    assert await text_in_database(database, "/etc/hosts") == []


async def test_a_server_the_catalogue_does_not_know_is_not_found_and_the_attempt_is_kept(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    server = FakeMcpServer()
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        stranger = await issue_key(app, other_tenant_id, AccessRole.DEVELOPER)
        await register(client, admin, grant={"scope_type": "tenant"})
        unknown = await call(client, admin, server="shadow-server")
        elsewhere = await call(client, stranger)

    assert (unknown.status_code, elsewhere.status_code) == (404, 404)
    assert unknown.json()["error"]["data"]["rules"] == ["MCP-SERVER-UNKNOWN"]
    rows = await invocations(database)
    assert [(row.target, row.target_known, row.outcome) for row in rows] == [
        ("shadow-server", False, "denied"),
        ("files", False, "denied"),
    ]
    assert rows[1].tenant_id == other_tenant_id
    assert [request.headers["mcp-method"] for request in server.requests] == [
        "server/discover",
        "tools/list",
    ]


@pytest.mark.parametrize(
    ("options", "status", "code"),
    [
        ({"version": "2025-11-25"}, 400, -32022),
        ({"headers": {"mcp-method": "tools/list"}}, 400, -32020),
        ({"headers": {"mcp-name": "write"}}, 400, -32020),
        ({"headers": {"origin": "https://evil.example"}}, 403, DENIED),
    ],
)
async def test_a_request_that_breaks_the_protocol_is_rejected_before_any_decision(
    database: Database, tenant_id: UUID, options: dict[str, Any], status: int, code: int
) -> None:
    server = FakeMcpServer()
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        before = len(server.requests)
        response = await call(client, admin, **options)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert len(server.requests) == before
    assert await invocations(database) == []


async def test_other_verbs_too_large_bodies_and_missing_keys_are_refused(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer()
    app = app_with(server, database, mcp={"max_request_bytes": 2048})
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        body, headers = mcp_request("tools/call", name="read")
        get = await client.get("/mcp/files", headers=admin.auth)
        delete = await client.delete("/mcp/files", headers=admin.auth)
        anonymous = await client.post("/mcp/files", content=body, headers=headers)
        large = await call(client, admin, arguments={"blob": "x" * 4096})
        supported = await call(client, admin, version="2024-11-05")

    assert (get.status_code, delete.status_code) == (405, 405)
    assert anonymous.status_code == 401
    assert large.status_code == 413
    assert supported.json()["error"]["data"]["supported"] == [REVISION]


async def test_an_event_stream_is_relayed_as_it_is_and_marked_as_streamed(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer(stream=True)
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        response = await call(client, admin)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    events = [line for line in response.text.splitlines() if line.startswith("data:")]
    assert "notifications/progress" in events[0]
    assert json.loads(events[1][5:])["result"]["content"][0]["text"] == "ran read"
    (row,) = await invocations(database)
    assert (row.outcome, row.streamed, row.response_bytes) == ("ok", True, len(response.content))


@pytest.mark.parametrize(
    ("server", "reason"),
    [
        (FakeMcpServer(fail=httpx.ConnectError("refused")), "ConnectError"),
        (FakeMcpServer(fail=httpx.ReadTimeout("slow")), "ReadTimeout"),
        (FakeMcpServer(redirect=True), "Redirect"),
    ],
)
async def test_a_server_that_fails_or_redirects_is_a_bad_gateway_and_is_recorded(
    database: Database, tenant_id: UUID, server: FakeMcpServer, reason: str
) -> None:
    server.requests.clear()
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"}, discover=False)
        response = await call(client, admin)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == -32011
    assert "refused" not in response.text
    # A redirect is not followed: the credential goes nowhere the catalogue did not name.
    assert len(server.requests) == 1
    (row,) = await invocations(database)
    assert (row.outcome, row.reason) == ("error", reason)
    (entry,) = await audit(database)
    assert entry.outcome == "allow"


async def test_an_error_of_the_server_is_passed_on_and_recorded_as_an_error(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer()
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        response = await call(client, admin, "completion/complete")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == -32601
    (row,) = await invocations(database)
    assert (row.outcome, row.reason, row.status_code) == ("error", "http_404", 404)


async def test_a_legacy_server_is_recorded_as_such_and_cannot_be_called(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer(legacy=True)
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        listed = (await client.get("/api/v1/mcp/servers/files", headers=admin.auth)).json()
        response = await call(client, admin)

    assert (listed["governability"], listed["protocol_versions"]) == ("legacy_only", ["legacy"])
    assert response.status_code == 403
    assert response.json()["error"]["data"]["rules"] == ["MCP-SERVER-NOT-GOVERNABLE"]
    assert len(server.requests) == 1
    (discovered,) = await audit(database, "mcp_server.discovered")
    assert discovered.outcome == "legacy_only"


async def test_a_server_that_names_other_revisions_is_recorded_with_them(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer(versions=("2027-01-15",))
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin)
        listed = (await client.get("/api/v1/mcp/servers/files", headers=admin.auth)).json()

    assert (listed["governability"], listed["protocol_versions"]) == ("legacy_only", ["2027-01-15"])


async def test_discovery_reads_every_page_of_tools_and_is_for_admins(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer(tools=("a", "b", "c", "d", "e"), page_size=2)
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await register(client, admin)
        listed = (await client.get("/api/v1/mcp/servers/files", headers=admin.auth)).json()
        refused = await client.post("/api/v1/mcp/servers/files/discovery", headers=developer.auth)
        missing = await client.post("/api/v1/mcp/servers/nope/discovery", headers=admin.auth)

    assert listed["tools"] == ["a", "b", "c", "d", "e"]
    assert (refused.status_code, missing.status_code) == (403, 404)


async def test_a_system_classified_as_prohibited_reaches_no_tool(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer()
    app = app_with(server, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        prohibited = await key_for_system(app, client, tenant_id, admin, "call-centre-mood-monitor")
        minimal = await key_for_system(app, client, tenant_id, admin, "invoice-data-extraction")
        await register(client, admin, grant={"scope_type": "tenant"})
        denied = await call(client, prohibited)
        allowed = await call(client, minimal)

    assert (denied.status_code, allowed.status_code) == (403, 200)
    assert denied.json()["error"]["data"]["rules"] == ["MCP-SYSTEM-PROHIBITED"]
    assert "indicative" in denied.json()["error"]["message"]


async def test_the_proxy_is_served_only_by_a_process_with_its_role(
    database: Database, tenant_id: UUID
) -> None:
    server = FakeMcpServer()
    app = app_with(server, database, server={"roles": ["gateway", "admin"]})
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        response = await call(client, admin)

    assert response.status_code == 404
    assert await invocations(database) == []
