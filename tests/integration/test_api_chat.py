import json
from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")

from sqlalchemy import select

from ai_arbiter import __version__
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.database import Database
from tests.api_support import ECHO, MOCK, app_for, issue_key, running
from tests.support import text_in_database

pytestmark = pytest.mark.usefixtures("gateway_secrets")

BODY = {"model": "gpt-test", "messages": [{"role": "user", "content": "Hello"}]}
EMAIL = "mario.rossi@example.com"


def events(text: str) -> list[str]:
    return [line.removeprefix("data: ") for line in text.splitlines() if line.startswith("data: ")]


async def test_a_request_without_a_key_is_refused(database: Database) -> None:
    async with running(app_for(database.engine.url.render_as_string(False))) as client:
        response = await client.post("/v1/chat/completions", json=BODY)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert (problem["status"], problem["code"]) == (401, "invalid_api_key")
    assert problem["error"]["message"] == problem["detail"]


@pytest.mark.parametrize("header", ["Bearer arb_nope", "Basic abc", "Bearer ", "arb_justthekey"])
async def test_a_wrong_key_is_refused(database: Database, header: str) -> None:
    async with running(app_for(database.engine.url.render_as_string(False))) as client:
        response = await client.post(
            "/v1/chat/completions", json=BODY, headers={"Authorization": header}
        )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_api_key"


async def test_a_key_without_a_role_for_the_data_plane_is_forbidden(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(database.engine.url.render_as_string(False))
    async with running(app) as client:
        no_role = await issue_key(app, tenant_id)
        auditor = await issue_key(app, tenant_id, AccessRole.AUDITOR)
        responses = [
            await client.post("/v1/chat/completions", json=BODY, headers=key.auth)
            for key in (no_role, auditor)
        ]

    assert [response.status_code for response in responses] == [403, 403]
    assert responses[0].json()["detail"] == "this operation needs the role admin or developer"


async def test_a_completion_is_returned_with_the_ids_to_find_it_again(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(database.engine.url.render_as_string(False))
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        response = await client.post("/v1/chat/completions", json=BODY, headers=key.auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["usage"]["total_tokens"] > 0
    assert response.headers["x-arbiter-policy"] == "allow"
    assert response.headers["x-arbiter-budget"] == "ok"
    assert "x-arbiter-redacted" not in response.headers
    async with database.session() as session:
        interaction = (await session.scalars(select(Interaction))).one()
    assert str(interaction.id) == response.headers["x-arbiter-interaction-id"]
    assert str(interaction.decision_id) == response.headers["x-arbiter-decision-id"]
    assert (interaction.project_id, interaction.principal_id) == (key.project_id, key.principal_id)


async def test_personal_data_in_the_prompt_is_redacted_and_reported_in_a_header(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(database.engine.url.render_as_string(False), ECHO)
    body = {**BODY, "messages": [{"role": "user", "content": f"Write to {EMAIL}"}]}
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        response = await client.post("/v1/chat/completions", json=body, headers=key.auth)

    assert response.json()["choices"][0]["message"]["content"] == "Write to [EMAIL]"
    assert response.headers["x-arbiter-policy"] == "redact"
    assert response.headers["x-arbiter-redacted"] == "email"
    assert await text_in_database(database, EMAIL) == []


async def test_a_request_denied_by_policy_explains_itself(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(database.engine.url.render_as_string(False), policy={"allowed_models": ["other"]})
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        english = await client.post("/v1/chat/completions", json=BODY, headers=key.auth)
        italian = await client.post(
            "/v1/chat/completions", json=BODY, headers={**key.auth, "Accept-Language": "it-IT"}
        )

    assert english.status_code == 403
    problem = english.json()
    assert problem["code"] == "policy_denied"
    assert problem["decision_id"] == english.headers["x-arbiter-decision-id"]
    assert problem["interaction_id"] == english.headers["x-arbiter-interaction-id"]
    assert problem["reasons"] == [
        {
            "rule_id": "POL-MODEL-NOT-ALLOWED",
            "pack": "policy",
            "pack_version": problem["reasons"][0]["pack_version"],
            "outcome": "deny",
            "message": "The requested model is not on the allowlist of this deployment.",
            "legal_refs": [],
        }
    ]
    assert problem["error"]["message"] == problem["reasons"][0]["message"]
    assert italian.json()["reasons"][0]["message"].startswith("Il modello richiesto non è")


async def test_an_unknown_model_is_not_found(database: Database, tenant_id: UUID) -> None:
    app = app_for(database.engine.url.render_as_string(False))
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        response = await client.post(
            "/v1/chat/completions", json={**BODY, "model": "nope"}, headers=key.auth
        )

    assert response.status_code == 404
    assert response.json()["code"] == "model_not_found"
    assert response.json()["detail"] == "no deployment serves the model 'nope'"


async def test_a_failing_provider_is_a_bad_gateway_with_the_decision_id(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(
        database.engine.url.render_as_string(False), {**MOCK, "settings": {"fail": "retryable"}}
    )
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        response = await client.post("/v1/chat/completions", json=BODY, headers=key.auth)

    assert response.status_code == 502
    assert response.json()["code"] == "upstream_error"
    assert UUID(response.json()["decision_id"])


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"messages": [{"role": "user", "content": "SECRET PROMPT"}]}, "body.model"),
        ({"model": "gpt-test", "messages": []}, "body.messages"),
        ({"model": "gpt-test", "messages": "SECRET PROMPT"}, "body.messages"),
        ({"model": "", "messages": [{"role": "user", "content": "SECRET PROMPT"}]}, "body.model"),
    ],
)
async def test_an_invalid_request_names_the_field_and_does_not_echo_the_input(
    database: Database, tenant_id: UUID, body: dict[str, object], field: str
) -> None:
    app = app_for(database.engine.url.render_as_string(False))
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        response = await client.post("/v1/chat/completions", json=body, headers=key.auth)

    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "invalid_request"
    assert problem["invalid"][0]["field"] == field
    assert "SECRET PROMPT" not in response.text


async def test_a_stream_is_sent_as_server_sent_events(database: Database, tenant_id: UUID) -> None:
    app = app_for(
        database.engine.url.render_as_string(False),
        {**MOCK, "settings": {"reply": "one two three"}},
    )
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        response = await client.post(
            "/v1/chat/completions", json={**BODY, "stream": True}, headers=key.auth
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-arbiter-policy"] == "allow"
    received = events(response.text)
    assert received[-1] == "[DONE]"
    chunks = [json.loads(event) for event in received[:-1]]
    assert "".join(c["choices"][0]["delta"].get("content", "") for c in chunks) == "one two three"
    assert all(chunk["choices"] for chunk in chunks)
    async with database.session() as session:
        interaction = (await session.scalars(select(Interaction))).one()
    assert (interaction.status, interaction.streamed) == ("ok", True)
    assert interaction.output_tokens is not None


async def test_a_stream_includes_usage_when_the_client_asks_for_it(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(database.engine.url.render_as_string(False))
    body = {**BODY, "stream": True, "stream_options": {"include_usage": True}}
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        response = await client.post("/v1/chat/completions", json=body, headers=key.auth)

    last = json.loads(events(response.text)[-2])
    assert last["choices"] == []
    assert last["usage"]["prompt_tokens"] > 0


async def test_a_stream_that_breaks_halfway_ends_with_an_error_event(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(
        database.engine.url.render_as_string(False),
        {**MOCK, "settings": {"reply": "one two three", "break_stream_after": 2}},
    )
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        response = await client.post(
            "/v1/chat/completions", json={**BODY, "stream": True}, headers=key.auth
        )

    received = events(response.text)
    assert response.status_code == 200
    assert received[-1] == "[DONE]"
    assert json.loads(received[-2]) == {
        "error": {"message": "the model provider ended the stream", "type": "upstream_error"}
    }
    async with database.session() as session:
        interaction = (await session.scalars(select(Interaction))).one()
    assert interaction.status == "error"


async def test_a_stream_denied_by_policy_is_a_plain_error_response(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(database.engine.url.render_as_string(False), policy={"allowed_models": []})
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        response = await client.post(
            "/v1/chat/completions", json={**BODY, "stream": True}, headers=key.auth
        )

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"


async def test_models_lists_what_is_served_and_allowed(database: Database, tenant_id: UUID) -> None:
    url = database.engine.url.render_as_string(False)
    second = {**MOCK, "name": "other", "serves": ["gpt-other"]}
    everything = app_for(url, MOCK, second)
    restricted = app_for(url, MOCK, second, policy={"allowed_models": ["gpt-other"]})
    async with running(everything) as client:
        key = await issue_key(everything, tenant_id, AccessRole.DEVELOPER)
        all_models = (await client.get("/v1/models", headers=key.auth)).json()
    async with running(restricted) as client:
        allowed_models = (await client.get("/v1/models", headers=key.auth)).json()

    assert all_models == {
        "object": "list",
        "data": [
            {"id": "gpt-other", "object": "model", "owned_by": "arbiter"},
            {"id": "gpt-test", "object": "model", "owned_by": "arbiter"},
        ],
    }
    assert [model["id"] for model in allowed_models["data"]] == ["gpt-other"]


async def test_a_revoked_key_stops_working_at_once(database: Database, tenant_id: UUID) -> None:
    app = app_for(database.engine.url.render_as_string(False))
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        before = await client.get("/v1/models", headers=key.auth)
        runtime = app.state.runtime
        async with runtime.database.transaction() as session:
            await runtime.identity.revoke_api_key(session, tenant_id, key.key_id)
        after = await client.get("/v1/models", headers=key.auth)

    assert (before.status_code, after.status_code) == (200, 401)


async def test_a_process_serves_only_the_parts_its_roles_name(
    database: Database, tenant_id: UUID
) -> None:
    url = database.engine.url.render_as_string(False)
    data_plane = app_for(url, server={"roles": ["gateway"]})
    control_plane = app_for(url, server={"roles": ["admin"]})
    async with running(data_plane) as client:
        key = await issue_key(data_plane, tenant_id, AccessRole.ADMIN)
        gateway_only = [
            (await client.get("/v1/models", headers=key.auth)).status_code,
            (await client.get("/api/v1/me", headers=key.auth)).status_code,
            (await client.get("/healthz")).status_code,
        ]
    async with running(control_plane) as client:
        admin_only = [
            (await client.get("/v1/models", headers=key.auth)).status_code,
            (await client.get("/api/v1/me", headers=key.auth)).status_code,
            (await client.get("/healthz")).status_code,
        ]

    assert gateway_only == [200, 404, 200]
    assert admin_only == [404, 200, 200]


async def test_an_unknown_path_is_a_problem_document_too(database: Database) -> None:
    async with running(app_for(database.engine.url.render_as_string(False))) as client:
        response = await client.get("/v1/nothing-here")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 404


async def test_the_openapi_document_describes_both_planes(database: Database) -> None:
    async with running(app_for(database.engine.url.render_as_string(False))) as client:
        document = (await client.get("/openapi.json")).json()

    assert document["info"]["version"] == __version__
    assert "not provide legal advice" in document["info"]["description"]
    assert {
        "/v1/chat/completions",
        "/v1/models",
        "/api/v1/api-keys",
        "/api/v1/budgets",
        "/api/v1/usage",
        "/api/v1/audit/verify",
        "/api/v1/audit/export",
    } <= set(document["paths"])
    for path, operations in document["paths"].items():
        for operation in operations.values():
            assert operation.get("summary"), path
            assert operation.get("tags"), path
