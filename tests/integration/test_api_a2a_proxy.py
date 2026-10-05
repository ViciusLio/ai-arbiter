"""The A2A proxy end to end, against a stand-in agent: decide, record, forward."""

import json
from typing import Any
from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")
pytest.importorskip("a2a", reason="needs the a2a extra")

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from ai_arbiter.core.audit import AuditEntry
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.invocation import Invocation
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.gateway.api.app import create_app
from tests.a2a_support import CARD, SigningKey, tampered, unsigned
from tests.api_support import Issued, gateway_settings, issue_key, running
from tests.integration.test_api_compliance import key_for_system, url_of
from tests.support import text_in_database

pytestmark = pytest.mark.usefixtures("gateway_secrets")

CARD_URL = "https://agent.example.org/.well-known/agent-card.json"
RPC_URL = "https://agent.example.org/a2a/v1"
REST_URL = "https://agent.example.org/a2a/rest"
DENIED = -32000
# Not a credential of anything: what the stand-in agent expects in these tests.
AGENT_TOKEN = "-".join(["agent", "token", "for", "tests"])


class FakeAgent:
    """Serves a card and answers the two bindings, remembering what it was asked."""

    def __init__(
        self,
        card: bytes | None = None,
        *,
        fail: Exception | None = None,
        redirect: bool = False,
    ) -> None:
        self.card = card if card is not None else unsigned()
        self.fail = fail
        self.redirect = redirect
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == CARD_URL:
            return httpx.Response(200, content=self.card)
        self.calls.append(request)
        if self.fail is not None:
            raise self.fail
        if self.redirect:
            return httpx.Response(307, headers={"location": "https://elsewhere.example/a2a"})
        task = {"task": {"id": "task-1", "status": {"state": "TASK_STATE_COMPLETED"}}}
        if str(request.url) == RPC_URL:
            body = json.loads(request.content)
            answer = {"jsonrpc": "2.0", "id": body["id"], "result": task}
            if body["method"] == "SendStreamingMessage":
                events = f"data: {json.dumps(answer)}\n\n"
                return httpx.Response(
                    200, headers={"content-type": "text/event-stream"}, content=events.encode()
                )
            return httpx.Response(200, json=answer)
        return httpx.Response(200, json=task)


def app_with(agent: FakeAgent, database: Database, *keys: SigningKey, **overrides: Any) -> FastAPI:
    settings = gateway_settings(
        url_of(database),
        a2a={"trusted_keys": [{"kid": key.kid, "jwk": key.jwk} for key in keys]},
        **overrides,
    )
    return create_app(settings, a2a_transport=httpx.MockTransport(agent))


async def register(
    client: httpx.AsyncClient, admin: Issued, *, grant: dict[str, Any] | None = None, **values: Any
) -> dict[str, Any]:
    body = {"key": "routes", "name": "Route planner", "card_url": CARD_URL, **values}
    created = await client.post("/api/v1/a2a/agents", json=body, headers=admin.auth)
    assert created.status_code == 201, created.text
    read = await client.post("/api/v1/a2a/agents/routes/card", headers=admin.auth)
    assert read.status_code == 200, read.text
    if grant is not None:
        given = await client.post(
            "/api/v1/a2a/agents/routes/grants", json=grant, headers=admin.auth
        )
        assert given.status_code == 201, given.text
    return dict(read.json())


def rpc(method: str = "SendMessage", text: str = "Plan a route home") -> bytes:
    params = {"message": {"role": "ROLE_USER", "parts": [{"text": text}]}}
    return json.dumps({"jsonrpc": "2.0", "id": 7, "method": method, "params": params}).encode()


async def call(
    client: httpx.AsyncClient,
    key: Issued,
    method: str = "SendMessage",
    *,
    agent: str = "routes",
    **headers: str,
) -> httpx.Response:
    sent = {"content-type": "application/json", "a2a-version": "1.0", **key.auth, **headers}
    return await client.post(f"/a2a/{agent}", content=rpc(method), headers=sent)


async def invocations(database: Database) -> list[Invocation]:
    async with database.session() as session:
        rows = await session.scalars(
            select(Invocation).order_by(Invocation.started_at, Invocation.id)
        )
        return list(rows.all())


async def test_a_granted_message_is_forwarded_with_the_credential_of_the_registry_and_recorded(
    database: Database, tenant_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ARBITER_SECRET_ROUTES_TOKEN", AGENT_TOKEN)
    agent = FakeAgent()
    app = app_with(agent, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await register(
            client, admin, grant={"scope_type": "tenant"}, credential="secret://routes-token"
        )
        response = await call(client, developer)

    assert response.status_code == 200, response.text
    assert response.json()["result"]["task"]["id"] == "task-1"
    (forwarded,) = agent.calls
    assert (forwarded.method, str(forwarded.url)) == ("POST", RPC_URL)
    assert forwarded.content == rpc()
    assert forwarded.headers["authorization"] == f"Bearer {AGENT_TOKEN}"
    assert forwarded.headers["a2a-version"] == "1.0"
    assert developer.key not in str(forwarded.headers)
    (row,) = await invocations(database)
    assert (row.protocol, row.target, row.method, row.name) == (
        "a2a",
        "routes",
        "send_message",
        None,
    )
    assert (row.outcome, row.status_code, row.project_id) == ("ok", 200, developer.project_id)
    async with database.session() as session:
        entry = (
            await session.scalars(select(AuditEntry).where(AuditEntry.action == "a2a.call"))
        ).one()
    assert (entry.outcome, entry.resource_id) == ("allow", str(row.id))
    assert entry.decision is not None
    assert entry.decision["details"]["card_verification"] == "unsigned"
    # What was said to the agent and what it answered are nowhere in the database.
    assert await text_in_database(database, "Plan a route home") == []
    assert await text_in_database(database, "TASK_STATE_COMPLETED") == []
    assert await text_in_database(database, AGENT_TOKEN) == []


async def test_without_a_grant_or_for_an_unknown_agent_nothing_is_forwarded(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    agent = FakeAgent()
    app = app_with(agent, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        stranger = await issue_key(app, other_tenant_id, AccessRole.DEVELOPER)
        await register(client, admin)
        refused = await call(client, admin, **{"accept-language": "it"})
        unknown = await call(client, admin, agent="shadow-agent")
        elsewhere = await call(client, stranger)

    assert (refused.status_code, unknown.status_code, elsewhere.status_code) == (403, 404, 404)
    error = refused.json()["error"]
    assert (error["code"], refused.json()["id"]) == (DENIED, 7)
    assert error["data"]["rules"] == ["A2A-CALL-NOT-GRANTED"]
    assert error["message"].startswith("Nessuna autorizzazione")
    assert unknown.json()["error"]["data"]["rules"] == ["A2A-AGENT-UNKNOWN"]
    assert agent.calls == []
    rows = await invocations(database)
    assert [(row.target, row.target_known, row.outcome, row.reason) for row in rows] == [
        ("routes", True, "denied", "A2A-CALL-NOT-GRANTED"),
        ("shadow-agent", False, "denied", "A2A-AGENT-UNKNOWN"),
        ("routes", False, "denied", "A2A-AGENT-UNKNOWN"),
    ]


async def test_only_the_operations_a2a_defines_are_forwarded(
    database: Database, tenant_id: UUID
) -> None:
    agent = FakeAgent()
    app = app_with(agent, database)
    cases = [
        ("GET", "tasks/task-1", 200),
        ("GET", "tasks", 200),
        ("POST", "tasks/task-1:cancel", 200),
        ("GET", "extendedAgentCard", 200),
        ("GET", "tasks/a/b/c", 404),
        ("GET", "tasks/..%2F..%2Fadmin", 404),
        ("DELETE", "tasks/task-1", 404),
        ("GET", "admin", 404),
    ]
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        unknown = await call(client, admin, "DeleteEverything")
        batch = await client.post("/a2a/routes", content=b"[]", headers=admin.auth)
        codes = [
            (await client.request(verb, f"/a2a/routes/rest/{path}", headers=admin.auth)).status_code
            for verb, path, _ in cases
        ]

    assert (unknown.status_code, unknown.json()["error"]["code"]) == (404, -32601)
    assert (batch.status_code, batch.json()["error"]["code"]) == (400, -32600)
    assert codes == [expected for _, _, expected in cases]
    assert [str(request.url) for request in agent.calls] == [
        f"{REST_URL}/tasks/task-1",
        f"{REST_URL}/tasks",
        f"{REST_URL}/tasks/task-1:cancel",
        f"{REST_URL}/extendedAgentCard",
    ]
    assert [row.method for row in await invocations(database)] == [
        "get_task",
        "list_tasks",
        "cancel_task",
        "get_extended_card",
    ]


async def test_the_http_json_binding_keeps_the_path_the_query_and_the_body(
    database: Database, tenant_id: UUID
) -> None:
    agent = FakeAgent()
    app = app_with(agent, database)
    body = json.dumps({"message": {"role": "ROLE_USER", "parts": [{"text": "A private note"}]}})
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        sent = await client.post(
            "/a2a/routes/rest/message:send",
            content=body,
            headers={"content-type": "application/json", **admin.auth},
        )
        listed = await client.get(
            "/a2a/routes/rest/tasks?pageSize=5&status=TASK_STATE_WORKING", headers=admin.auth
        )

    assert (sent.status_code, listed.status_code) == (200, 200)
    first, second = agent.calls
    assert (first.method, str(first.url), first.content.decode()) == (
        "POST",
        f"{REST_URL}/message:send",
        body,
    )
    assert str(second.url) == f"{REST_URL}/tasks?pageSize=5&status=TASK_STATE_WORKING"
    assert admin.key not in str(first.headers)
    assert await text_in_database(database, "A private note") == []


async def test_a_push_configuration_is_not_created_through_the_proxy(
    database: Database, tenant_id: UUID
) -> None:
    agent = FakeAgent()
    app = app_with(agent, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        over_rpc = await call(client, admin, "CreateTaskPushNotificationConfig")
        over_rest = await client.post(
            "/a2a/routes/rest/tasks/task-1/pushNotificationConfigs",
            content=b"{}",
            headers=admin.auth,
        )
        reading = await client.get(
            "/a2a/routes/rest/tasks/task-1/pushNotificationConfigs", headers=admin.auth
        )

    assert (over_rpc.status_code, over_rest.status_code, reading.status_code) == (403, 403, 200)
    assert over_rpc.json()["error"]["data"]["rules"] == ["A2A-PUSH-NOT-ALLOWED"]
    assert over_rest.json()["rules"] == ["A2A-PUSH-NOT-ALLOWED"]
    assert [request.method for request in agent.calls] == ["GET"]


@pytest.mark.parametrize(
    ("case", "status", "rules"),
    [
        ("verified", 200, []),
        ("unsigned", 200, []),
        ("stranger", 200, []),
        ("tampered", 403, ["A2A-CARD-NOT-TRUSTED"]),
    ],
)
async def test_an_agent_whose_card_was_altered_is_not_called(
    database: Database, tenant_id: UUID, case: str, status: int, rules: list[str]
) -> None:
    trusted, stranger = SigningKey("key-1"), SigningKey("their-key")
    card = {
        "verified": trusted.sign(CARD),
        "unsigned": unsigned(),
        "stranger": stranger.sign(CARD),
        "tampered": tampered(trusted.sign(CARD), version="6.6.6"),
    }[case]
    agent = FakeAgent(card)
    app = app_with(agent, database, trusted)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        response = await call(client, admin)

    assert response.status_code == status
    assert (response.json().get("error") or {}).get("data", {}).get("rules", []) == rules
    assert len(agent.calls) == (1 if status == 200 else 0)


async def test_an_agent_is_called_only_on_a_binding_its_card_lists_on_its_own_host(
    database: Database, tenant_id: UUID
) -> None:
    rpc_only = {**CARD, "supportedInterfaces": [CARD["supportedInterfaces"][0]]}
    grpc_only = {
        **CARD,
        "supportedInterfaces": [
            {
                "url": "https://agent.example.org/grpc",
                "protocolBinding": "GRPC",
                "protocolVersion": "1.0",
            }
        ],
    }
    first, second = FakeAgent(unsigned(rpc_only)), FakeAgent(unsigned(grpc_only))
    results = []
    for agent in (first, second):
        app = app_with(agent, database)
        async with running(app) as client:
            admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
            if agent is second:
                await client.delete("/api/v1/a2a/agents/routes", headers=admin.auth)
            await register(client, admin, grant={"scope_type": "tenant"})
            over_rpc = await call(client, admin)
            over_rest = await client.get("/a2a/routes/rest/tasks", headers=admin.auth)
            results.append((over_rpc.status_code, over_rest.status_code))
            if over_rest.status_code == 403:
                assert over_rest.json()["rules"] == ["A2A-AGENT-NOT-GOVERNABLE"]

    assert results == [(200, 403), (403, 403)]
    assert len(first.calls) == 1
    assert second.calls == []


async def test_a_stream_is_relayed_and_a_failing_agent_is_a_bad_gateway(
    database: Database, tenant_id: UUID
) -> None:
    streaming = FakeAgent()
    app = app_with(streaming, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await register(client, admin, grant={"scope_type": "tenant"})
        stream = await call(client, admin, "SendStreamingMessage")
        streaming.fail = httpx.ConnectError("refused")
        down = await call(client, admin)
        streaming.fail, streaming.redirect = None, True
        redirected = await call(client, admin)

    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert json.loads(stream.text.split("data: ")[1])["result"]["task"]["id"] == "task-1"
    assert (down.status_code, redirected.status_code) == (502, 502)
    assert "refused" not in down.text
    rows = await invocations(database)
    assert [(row.method, row.outcome, row.reason, row.streamed) for row in rows] == [
        ("send_streaming_message", "ok", None, True),
        ("send_message", "error", "ConnectError", False),
        ("send_message", "error", "Redirect", False),
    ]
    # The redirect was not followed.
    assert len(streaming.calls) == 3


async def test_a_prohibited_system_calls_no_agent_and_the_proxy_needs_its_role(
    database: Database, tenant_id: UUID
) -> None:
    agent = FakeAgent()
    app = app_with(agent, database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        prohibited = await key_for_system(app, client, tenant_id, admin, "call-centre-mood-monitor")
        await register(client, admin, grant={"scope_type": "tenant"})
        denied = await call(client, prohibited)
        browser = await call(client, admin, origin="https://evil.example")
    without_role = app_with(agent, database, server={"roles": ["gateway", "admin"]})
    async with running(without_role) as client:
        absent = await call(client, admin)

    assert denied.status_code == 403
    assert denied.json()["error"]["data"]["rules"] == ["A2A-SYSTEM-PROHIBITED"]
    assert (browser.status_code, absent.status_code) == (403, 404)
    assert agent.calls == []
