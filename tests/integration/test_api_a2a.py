"""The A2A registry over HTTP: agents, their card and its signatures, grants."""

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
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.gateway.api.app import create_app
from tests.a2a_support import CARD, SigningKey, tampered, unsigned
from tests.api_support import Issued, gateway_settings, issue_key, running
from tests.integration.test_api_compliance import declare, url_of
from tests.support import text_in_database

pytestmark = pytest.mark.usefixtures("gateway_secrets")

CARD_URL = "https://agent.example.org/.well-known/agent-card.json"
AGENT = {"key": "routes", "name": "Route planner", "card_url": CARD_URL}


class CardHost:
    """Serves one document at the card address and remembers what it was asked."""

    def __init__(self, document: bytes, *, status: int = 200) -> None:
        self.document = document
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status in (301, 302):
            return httpx.Response(self.status, headers={"location": "https://elsewhere.example"})
        return httpx.Response(self.status, content=self.document)


def app_with(host: CardHost, database: Database, *keys: SigningKey, **a2a: Any) -> FastAPI:
    settings = gateway_settings(
        url_of(database),
        a2a={"trusted_keys": [{"kid": key.kid, "jwk": key.jwk} for key in keys], **a2a},
    )
    return create_app(settings, a2a_transport=httpx.MockTransport(host))


async def register(client: httpx.AsyncClient, admin: Issued, **values: Any) -> httpx.Response:
    created = await client.post("/api/v1/a2a/agents", json={**AGENT, **values}, headers=admin.auth)
    assert created.status_code == 201, created.text
    return await client.post("/api/v1/a2a/agents/routes/card", headers=admin.auth)


async def test_a_card_signed_with_a_trusted_key_makes_a_verified_governable_agent(
    database: Database, tenant_id: UUID
) -> None:
    key = SigningKey()
    host = CardHost(key.sign(CARD))
    app = app_with(host, database, key)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        auditor = await issue_key(app, tenant_id, AccessRole.AUDITOR)
        await declare(client, admin, "cv-screening")
        created = await client.post(
            "/api/v1/a2a/agents",
            json={**AGENT, "ai_system": "cv-screening", "credential": "secret://routes-token"},
            headers=admin.auth,
        )
        read = await client.post("/api/v1/a2a/agents/routes/card", headers=admin.auth)
        listed = await client.get("/api/v1/a2a/agents", headers=auditor.auth)

    before, agent = created.json(), read.json()
    assert (before["verification"], before["governability"]) == ("not_fetched", "not_fetched")
    assert read.status_code == 200, read.text
    assert (agent["verification"], agent["signing_key_id"]) == ("verified", "key-1")
    assert (agent["governability"], agent["card_name"], agent["card_version"]) == (
        "governable",
        "Route planner",
        "1.4.0",
    )
    assert [(item["binding"], item["usable"]) for item in agent["interfaces"]] == [
        ("JSONRPC", True),
        ("HTTP+JSON", True),
    ]
    assert (agent["has_credential"], "credential" in agent) == (True, False)
    assert len(agent["card_sha256"]) == 64
    assert [item["key"] for item in listed.json()] == ["routes"]
    assert str(host.requests[0].url) == CARD_URL
    assert "authorization" not in host.requests[0].headers
    # What the card says of itself in words is not kept.
    assert await text_in_database(database, "Plans routes between two places") == []
    async with database.session() as session:
        entry = (
            await session.scalars(
                select(AuditEntry).where(AuditEntry.action == "a2a_agent.card_read")
            )
        ).one()
    assert entry.outcome == "verified"
    assert entry.decision is not None
    assert (entry.decision["changed"], entry.decision["governability"]) == (False, "governable")


@pytest.mark.parametrize(
    ("case", "verification"),
    [("unsigned", "unsigned"), ("stranger", "unknown_key"), ("tampered", "invalid")],
)
async def test_a_card_that_is_not_verified_is_registered_and_said_to_be_so(
    database: Database, tenant_id: UUID, case: str, verification: str
) -> None:
    trusted, stranger = SigningKey("key-1"), SigningKey("their-key")
    document = {
        "unsigned": unsigned(),
        "stranger": stranger.sign(CARD, jku="https://agent.example.org/jwks.json"),
        "tampered": tampered(trusted.sign(CARD), version="9.9.9"),
    }[case]
    host = CardHost(document)
    app = app_with(host, database, trusted)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        read = await register(client, admin)

    assert read.status_code == 200, read.text
    assert read.json()["verification"] == verification
    # Nothing was fetched but the card: the key set a card names is never asked for.
    assert [str(request.url) for request in host.requests] == [CARD_URL]


async def test_an_interface_on_another_host_or_over_grpc_is_not_usable(
    database: Database, tenant_id: UUID
) -> None:
    card = {
        **CARD,
        "supportedInterfaces": [
            {
                "url": "https://internal.corp.example/a2a",
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
            },
            {
                "url": "http://agent.example.org/a2a",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            },
            {
                "url": "https://agent.example.org:443/grpc",
                "protocolBinding": "GRPC",
                "protocolVersion": "1.0",
            },
        ],
    }
    app = app_with(CardHost(unsigned(card)), database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        read = await register(client, admin)

    agent = read.json()
    assert agent["governability"] == "no_proxied_binding"
    assert [item["usable"] for item in agent["interfaces"]] == [False, False, False]


@pytest.mark.parametrize(
    ("host", "problem"),
    [
        (CardHost(b"", status=404), "HTTP 404"),
        (CardHost(b"", status=302), "HTTP 302"),
        (CardHost(b"<html>not a card</html>"), "not an A2A Agent Card"),
        (CardHost(b"x" * 5000), "larger than a2a.max_card_bytes"),
    ],
)
async def test_a_card_that_cannot_be_read_leaves_the_agent_as_it_was(
    database: Database, tenant_id: UUID, host: CardHost, problem: str
) -> None:
    host.requests.clear()
    app = app_with(host, database, max_card_bytes=4096)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        read = await register(client, admin)
        agent = (await client.get("/api/v1/a2a/agents/routes", headers=admin.auth)).json()

    assert read.status_code == 409
    assert problem in read.json()["detail"]
    assert agent["verification"] == "not_fetched"
    # A redirect is not followed.
    assert len(host.requests) == 1


async def test_a_card_that_changes_is_read_again_and_the_change_is_audited(
    database: Database, tenant_id: UUID
) -> None:
    key = SigningKey()
    host = CardHost(key.sign(CARD))
    app = app_with(host, database, key)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        first = (await register(client, admin)).json()
        host.document = tampered(host.document, version="2.0.0")
        second = (await client.post("/api/v1/a2a/agents/routes/card", headers=admin.auth)).json()

    assert (first["verification"], second["verification"]) == ("verified", "invalid")
    assert first["card_sha256"] != second["card_sha256"]
    async with database.session() as session:
        entries = (
            await session.scalars(
                select(AuditEntry)
                .where(AuditEntry.action == "a2a_agent.card_read")
                .order_by(AuditEntry.seq)
            )
        ).all()
    assert [(entry.outcome, (entry.decision or {})["changed"]) for entry in entries] == [
        ("verified", False),
        ("invalid", True),
    ]


async def test_agents_and_grants_are_managed_by_an_admin_inside_one_tenant(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    app = app_with(CardHost(unsigned()), database)
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        auditor = await issue_key(app, tenant_id, AccessRole.AUDITOR)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        outsider = await issue_key(app, other_tenant_id, AccessRole.ADMIN)
        await register(client, admin)
        again = await client.post("/api/v1/a2a/agents", json=AGENT, headers=admin.auth)
        plain = await client.post(
            "/api/v1/a2a/agents",
            json={**AGENT, "key": "plain", "card_url": "http://agent.example.org/card.json"},
            headers=admin.auth,
        )
        grant = await client.post(
            "/api/v1/a2a/agents/routes/grants",
            json={"scope_type": "project", "scope_id": str(developer.project_id)},
            headers=admin.auth,
        )
        grants = await client.get("/api/v1/a2a/grants", headers=auditor.auth)
        codes = [
            (await client.post("/api/v1/a2a/agents", json=AGENT, headers=auditor.auth)).status_code,
            (await client.get("/api/v1/a2a/agents", headers=developer.auth)).status_code,
            (await client.post("/api/v1/a2a/agents/routes/card", headers=auditor.auth)).status_code,
            (await client.get("/api/v1/a2a/agents/routes", headers=outsider.auth)).status_code,
        ]
        elsewhere = (await client.get("/api/v1/a2a/agents", headers=outsider.auth)).json()
        revoked = await client.delete(
            f"/api/v1/a2a/grants/{grant.json()['id']}", headers=admin.auth
        )
        removed = await client.delete("/api/v1/a2a/agents/routes", headers=admin.auth)

    assert (again.status_code, plain.status_code) == (409, 409)
    assert "https" in plain.json()["detail"]
    assert grant.status_code == 201
    assert [item["agent"] for item in grants.json()] == ["routes"]
    assert codes == [403, 403, 403, 404]
    assert elsewhere == []
    assert (revoked.status_code, removed.status_code) == (204, 204)
