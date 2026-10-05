"""The A2A proxy between a client and a server of the official SDK (I-45).

Both are the real implementations: the client of ``a2a-sdk`` talks to Arbiter, and
Arbiter forwards to an agent built with the server side of ``a2a-sdk``, which also
serves its own card. They are joined in process, with no socket: the proxy reaches the
agent through an ASGI transport, and the client reaches Arbiter the same way. Nothing
here is a stand-in written by this project.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")
pytest.importorskip("a2a", reason="needs the a2a extra")
pytest.importorskip("sse_starlette", reason="needs the server side of the A2A SDK")

import httpx
from a2a.client import A2AClientError, ClientConfig, create_client
from a2a.helpers.proto_helpers import new_text_message
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandlerV2
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.routes.rest_routes import create_rest_routes
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCard, Role, SendMessageRequest
from google.protobuf import json_format
from sqlalchemy import select
from starlette.applications import Starlette

from ai_arbiter.core.audit import AuditEntry
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.invocation import Invocation
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.gateway.api.app import create_app
from tests.a2a_support import CARD
from tests.api_support import Issued, gateway_settings, issue_key
from tests.integration.test_api_compliance import url_of
from tests.support import text_in_database

pytestmark = pytest.mark.usefixtures("gateway_secrets")

CARD_URL = "https://agent.example.org/.well-known/agent-card.json"
ARBITER = "http://arbiter.test"


class RoutePlanner(AgentExecutor):
    """An agent of the SDK that answers every message with one message."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        asked = context.get_user_input()
        await event_queue.enqueue_event(new_text_message(f"route for: {asked}"))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def agent_card() -> AgentCard:
    return json_format.ParseDict(CARD, AgentCard())


def build_agent() -> Starlette:
    """The agent as the SDK serves it: its card and both HTTP bindings."""
    card = agent_card()
    handler = DefaultRequestHandlerV2(
        agent_executor=RoutePlanner(), task_store=InMemoryTaskStore(), agent_card=card
    )
    return Starlette(
        routes=[
            *create_agent_card_routes(card),
            *create_jsonrpc_routes(handler, rpc_url="/a2a/v1"),
            *create_rest_routes(handler, path_prefix="/a2a/rest"),
        ]
    )


@asynccontextmanager
async def stack(database: Database) -> AsyncIterator[tuple[Any, httpx.AsyncClient]]:
    """An agent of the SDK behind Arbiter, and a client for Arbiter's API."""
    upstream = build_agent()
    app = create_app(
        gateway_settings(url_of(database)), a2a_transport=httpx.ASGITransport(app=upstream)
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ARBITER) as admin_client,
    ):
        yield app, admin_client


async def register(client: httpx.AsyncClient, admin: Issued, **grant: Any) -> dict[str, Any]:
    created = await client.post(
        "/api/v1/a2a/agents",
        json={"key": "routes", "name": "Route planner", "card_url": CARD_URL},
        headers=admin.auth,
    )
    assert created.status_code == 201, created.text
    read = await client.post("/api/v1/a2a/agents/routes/card", headers=admin.auth)
    assert read.status_code == 200, read.text
    if grant:
        given = await client.post(
            "/api/v1/a2a/agents/routes/grants", json=grant, headers=admin.auth
        )
        assert given.status_code == 201, given.text
    return dict(read.json())


def card_through_arbiter(binding: str) -> AgentCard:
    """The card a client is configured with: the agent's, at the address of the proxy."""
    path = "/a2a/routes" if binding == "JSONRPC" else "/a2a/routes/rest"
    interface = {"url": f"{ARBITER}{path}", "protocolBinding": binding, "protocolVersion": "1.0"}
    return json_format.ParseDict({**CARD, "supportedInterfaces": [interface]}, AgentCard())


async def ask(app: Any, key: Issued, binding: str, text: str, *, streaming: bool) -> list[str]:
    """Send one message with the client of the SDK and return the texts it got back."""
    config = ClientConfig(
        streaming=streaming,
        supported_protocol_bindings=[binding],
        httpx_client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app), headers=key.auth),
    )
    client = await create_client(card_through_arbiter(binding), client_config=config)
    request = SendMessageRequest(message=new_text_message(text, role=Role.ROLE_USER))
    answers: list[str] = []
    async with client:
        async for event in client.send_message(request):
            answers.extend(part.text for part in event.message.parts)
    return answers


async def invocations(database: Database) -> list[Invocation]:
    async with database.session() as session:
        rows = await session.scalars(
            select(Invocation).order_by(Invocation.started_at, Invocation.id)
        )
        return list(rows.all())


async def test_the_card_a_real_agent_serves_is_read_and_its_interfaces_are_usable(
    database: Database, tenant_id: UUID
) -> None:
    async with stack(database) as (app, admin_client):
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        read = await register(admin_client, admin)

    assert read["card_name"] == "Route planner"
    assert read["governability"] == "governable"


@pytest.mark.parametrize(
    ("binding", "streaming", "method"),
    [
        ("JSONRPC", False, "send_message"),
        ("JSONRPC", True, "send_streaming_message"),
        ("HTTP+JSON", False, "send_message"),
        ("HTTP+JSON", True, "send_streaming_message"),
    ],
)
async def test_a_real_client_reaches_a_real_agent_through_the_proxy(
    database: Database, tenant_id: UUID, binding: str, streaming: bool, method: str
) -> None:
    async with stack(database) as (app, admin_client):
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await register(admin_client, admin, scope_type="tenant")
        answers = await ask(
            app, developer, binding, "to the house of ada lovelace", streaming=streaming
        )

    assert answers == ["route for: to the house of ada lovelace"]
    (row,) = await invocations(database)
    assert (row.protocol, row.target, row.method, row.outcome, row.status_code) == (
        "a2a",
        "routes",
        method,
        "ok",
        200,
    )
    async with database.session() as session:
        entries = (
            await session.scalars(select(AuditEntry).where(AuditEntry.action == "a2a.call"))
        ).all()
    assert len(entries) == 1
    assert await text_in_database(database, "ada lovelace") == []


@pytest.mark.parametrize("binding", ["JSONRPC", "HTTP+JSON"])
async def test_a_real_client_without_a_grant_is_refused_and_the_agent_is_not_called(
    database: Database, tenant_id: UUID, binding: str
) -> None:
    async with stack(database) as (app, admin_client):
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await register(admin_client, admin)
        with pytest.raises(A2AClientError) as refused:
            await ask(app, developer, binding, "secret destination", streaming=False)

    # The client of the SDK reports the status and drops the body, so the reason of the
    # refusal reaches the audit log and the invocation, not the person at the client.
    assert "403" in str(refused.value)
    (row,) = await invocations(database)
    assert (row.outcome, row.status_code) == ("denied", None)
    assert await text_in_database(database, "secret destination") == []
