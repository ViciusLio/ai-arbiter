from typing import Any
from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")

import httpx

from ai_arbiter.core.audit import verify_export
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.persistence.database import Database
from tests.api_support import Issued, app_for, issue_key, running

pytestmark = pytest.mark.usefixtures("gateway_secrets")

CHAT = {"model": "gpt-test", "messages": [{"role": "user", "content": "x" * 400}]}


def url_of(database: Database) -> str:
    return database.engine.url.render_as_string(False)


async def created(
    client: httpx.AsyncClient, path: str, admin: Issued, **body: object
) -> dict[str, Any]:
    response = await client.post(f"/api/v1{path}", json=body, headers=admin.auth)
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_me_shows_the_caller_as_the_gateway_sees_it(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.AUDITOR, AccessRole.DEVELOPER)
        response = await client.get("/api/v1/me", headers=key.auth)

    assert response.json() == {
        "tenant_id": str(tenant_id),
        "principal_id": str(key.principal_id),
        "team_id": str(key.team_id),
        "project_id": str(key.project_id),
        "ai_system_id": None,
        "key_id": key.key_id,
        "roles": ["auditor", "developer"],
    }


async def test_an_application_is_onboarded_through_the_api_and_can_then_call_a_model(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        team = await created(client, "/teams", admin, name="Customer care")
        project = await created(client, "/projects", admin, team_id=team["id"], name="Chatbot")
        principal = await created(
            client, "/principals", admin, kind="service", display_name="Chatbot backend"
        )
        role = await created(
            client,
            f"/principals/{principal['id']}/roles",
            admin,
            role="developer",
            scope_type="project",
            scope_id=project["id"],
        )
        issued = await created(
            client,
            "/api-keys",
            admin,
            project_id=project["id"],
            principal_id=principal["id"],
            name="production",
        )
        headers = {"Authorization": f"Bearer {issued['key']}"}
        answer = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        listed = (await client.get("/api/v1/api-keys", headers=admin.auth)).json()
        revoked = await client.delete(f"/api/v1/api-keys/{issued['key_id']}", headers=admin.auth)
        after = await client.post("/v1/chat/completions", json=CHAT, headers=headers)

    assert role["scope_id"] == project["id"]
    assert issued["key"].startswith(issued["prefix"] + "_")
    assert answer.status_code == 200, answer.text
    assert [key["name"] for key in listed] == ["test key", "production"]
    assert all("key" not in key and "key_hash" not in key for key in listed)
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert after.status_code == 401


async def test_lists_show_what_was_created(database: Database, tenant_id: UUID) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        team = await created(client, "/teams", admin, name="Zeta")
        await created(client, "/projects", admin, team_id=team["id"], name="Beta")
        teams = (await client.get("/api/v1/teams", headers=admin.auth)).json()
        projects = (await client.get("/api/v1/projects", headers=admin.auth)).json()
        principals = (await client.get("/api/v1/principals", headers=admin.auth)).json()

    assert "Zeta" in [item["name"] for item in teams]
    assert "Beta" in [item["name"] for item in projects]
    assert [item["kind"] for item in principals] == ["service"]


async def test_every_administrative_change_is_audited_without_names(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        team = await created(client, "/teams", admin, name="Team of Grace Hopper")
        await created(client, "/principals", admin, kind="user", display_name="Grace Hopper")
        entries = (await client.get("/api/v1/audit/entries", headers=admin.auth)).json()
        verification = (await client.get("/api/v1/audit/verify", headers=admin.auth)).json()

    assert [(e["seq"], e["action"], e["resource_type"]) for e in entries] == [
        (1, "team.created", "team"),
        (2, "principal.created", "principal"),
    ]
    assert entries[0]["resource_id"] == team["id"]
    assert entries[0]["actor_id"] == str(admin.principal_id)
    assert "Grace Hopper" not in str(entries)
    assert (verification["ok"], verification["entries"]) == (True, 2)
    assert "not proof" in verification["note"]


async def test_conflicts_and_missing_things_are_reported_as_such(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await created(client, "/teams", admin, name="Twice")
        duplicate = await client.post("/api/v1/teams", json={"name": "Twice"}, headers=admin.auth)
        orphan = await client.post(
            "/api/v1/projects", json={"team_id": str(new_id()), "name": "x"}, headers=admin.auth
        )
        missing_key = await client.delete("/api/v1/api-keys/nokeyhere", headers=admin.auth)
        naive = await client.post(
            "/api/v1/api-keys",
            json={
                "project_id": str(admin.project_id),
                "principal_id": str(admin.principal_id),
                "name": "n",
                "expires_at": "2030-01-01T00:00:00",
            },
            headers=admin.auth,
        )
        invalid = await client.post("/api/v1/teams", json={"name": ""}, headers=admin.auth)

    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "conflict")
    assert (orphan.status_code, orphan.json()["code"]) == (404, "not_found")
    assert missing_key.status_code == 404
    assert (naive.status_code, naive.json()["detail"]) == (409, "expires_at must carry a time zone")
    assert invalid.status_code == 422


async def test_only_an_admin_changes_things_and_an_auditor_can_read(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        auditor = await issue_key(app, tenant_id, AccessRole.AUDITOR)

        async def status(method: str, path: str, key: Issued) -> int:
            response = await client.request(
                method, f"/api/v1{path}", json={"name": "x"}, headers=key.auth
            )
            return response.status_code

        developer_codes = [
            await status("GET", "/teams", developer),
            await status("POST", "/teams", developer),
            await status("GET", "/usage", developer),
            await status("GET", "/audit/entries", developer),
            await status("GET", "/me", developer),
        ]
        auditor_codes = [
            await status("GET", "/teams", auditor),
            await status("POST", "/teams", auditor),
            await status("GET", "/usage", auditor),
            await status("GET", "/audit/entries", auditor),
            await status("GET", "/audit/verify", auditor),
            await status("GET", "/audit/export", auditor),
            await status("GET", "/budgets", auditor),
            await status("PUT", "/audit/fail-mode", auditor),
        ]

    assert developer_codes == [403, 403, 403, 403, 200]
    assert auditor_codes == [403, 403, 200, 200, 200, 200, 200, 403]


async def test_one_tenant_cannot_reach_another_through_the_api(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        mine = await issue_key(app, tenant_id, AccessRole.ADMIN)
        theirs = await issue_key(app, other_tenant_id, AccessRole.ADMIN)
        await created(client, "/teams", mine, name="Private team")
        await client.post("/v1/chat/completions", json=CHAT, headers=mine.auth)

        teams = (await client.get("/api/v1/teams", headers=theirs.auth)).json()
        keys = (await client.get("/api/v1/api-keys", headers=theirs.auth)).json()
        usage = (await client.get("/api/v1/usage", headers=theirs.auth)).json()
        entries = (await client.get("/api/v1/audit/entries", headers=theirs.auth)).json()
        revoke = await client.delete(f"/api/v1/api-keys/{mine.key_id}", headers=theirs.auth)
        project = await client.post(
            "/api/v1/projects",
            json={"team_id": str(mine.team_id), "name": "intruder"},
            headers=theirs.auth,
        )

    assert "Private team" not in [team["name"] for team in teams]
    assert [key["key_id"] for key in keys] == [theirs.key_id]
    assert usage["lines"] == []
    assert entries == []
    assert (revoke.status_code, project.status_code) == (404, 404)


async def test_a_hard_budget_is_created_seen_filling_up_and_then_denies(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        budget = await created(
            client,
            "/budgets",
            admin,
            scope_type="project",
            scope_id=str(admin.project_id),
            period="month",
            limit_amount="0.000025",
            hard=True,
        )
        first = await client.post("/v1/chat/completions", json=CHAT, headers=admin.auth)
        second = await client.post("/v1/chat/completions", json=CHAT, headers=admin.auth)
        third = await client.post("/v1/chat/completions", json=CHAT, headers=admin.auth)
        listed = (await client.get("/api/v1/budgets", headers=admin.auth)).json()
        deleted = await client.delete(f"/api/v1/budgets/{budget['id']}", headers=admin.auth)
        fourth = await client.post("/v1/chat/completions", json=CHAT, headers=admin.auth)

    assert (budget["spent"], budget["level"], budget["currency"]) == ("0", "ok", "USD")
    assert [first.status_code, second.status_code, third.status_code] == [200, 200, 403]
    assert first.headers["x-arbiter-budget"] == "ok"
    assert second.headers["x-arbiter-budget"] == "soft"
    assert third.json()["reasons"][0]["rule_id"] == "POL-BUDGET-EXCEEDED"
    assert (listed[0]["spent"], listed[0]["level"]) == ("0.0000408", "exceeded")
    assert listed[0]["limit_amount"] == "0.000025"
    assert deleted.status_code == 204
    assert fourth.status_code == 200


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"limit_amount": "abc"}, "limit_amount: 'abc' is not a decimal number"),
        ({"limit_amount": "0"}, "limit_amount: '0' must be greater than zero"),
        ({"currency": "GBP"}, "no conversion rate"),
        ({"scope_type": "team"}, "needs its id"),
    ],
)
async def test_a_budget_that_makes_no_sense_is_refused(
    database: Database, tenant_id: UUID, body: dict[str, object], detail: str
) -> None:
    app = app_for(url_of(database))
    values = {"scope_type": "tenant", "period": "day", "limit_amount": "10", **body}
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        response = await client.post("/api/v1/budgets", json=values, headers=admin.auth)

    assert response.status_code == 409
    assert detail in response.json()["detail"]


async def test_usage_is_reported_per_scope_with_names(database: Database, tenant_id: UUID) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await client.post("/v1/chat/completions", json=CHAT, headers=admin.auth)
        await client.post("/v1/chat/completions", json=CHAT, headers=admin.auth)
        by_project = (await client.get("/api/v1/usage", headers=admin.auth)).json()
        by_tenant = (
            await client.get("/api/v1/usage", params={"scope": "tenant"}, headers=admin.auth)
        ).json()
        by_principal = (
            await client.get("/api/v1/usage", params={"scope": "principal"}, headers=admin.auth)
        ).json()

    line = by_project["lines"][0]
    assert by_project["scope_type"] == "project"
    assert by_project["currency"] == "USD"
    assert "estimates" in by_project["note"]
    assert (line["scope_id"], line["name"]) == (str(admin.project_id), "assistant")
    assert (line["requests"], line["input_tokens"], line["cost_estimate"]) == (2, 200, "0.0000408")
    assert (line["unpriced"], line["estimated"], line["denied"]) == (0, 0, 0)
    assert by_tenant["lines"][0]["name"] == "Acme"
    assert by_principal["lines"][0]["name"] is None


async def test_the_usage_report_is_available_as_markdown_in_both_languages(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(
        url_of(database),
        finops={"reporting": {"currency": "EUR", "rate": "0.92", "rate_as_of": "2026-10-01"}},
    )
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await client.post("/v1/chat/completions", json=CHAT, headers=admin.auth)
        english = await client.get(
            "/api/v1/usage", params={"format": "markdown"}, headers=admin.auth
        )
        italian = await client.get(
            "/api/v1/usage", params={"format": "markdown", "locale": "it"}, headers=admin.auth
        )
        unsupported = await client.get("/api/v1/usage", params={"locale": "fr"}, headers=admin.auth)
        backwards = await client.get(
            "/api/v1/usage", params={"start": "2026-10-02", "end": "2026-10-01"}, headers=admin.auth
        )

    assert english.headers["content-type"] == "text/markdown; charset=utf-8"
    assert english.text.startswith("# Usage report")
    assert "| assistant | 1 |" in english.text
    assert "Estimated cost (EUR)" in english.text
    assert "does not provide legal advice" in english.text
    assert italian.text.startswith("# Report dei consumi")
    assert "Non fornisce consulenza legale" in italian.text
    assert (unsupported.status_code, backwards.status_code) == (409, 409)


async def test_the_audit_log_is_paged_and_its_export_verifies_elsewhere(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        for _ in range(3):
            await client.post("/v1/chat/completions", json=CHAT, headers=admin.auth)
        page = (
            await client.get(
                "/api/v1/audit/entries", params={"after": 2, "limit": 3}, headers=admin.auth
            )
        ).json()
        export = await client.get("/api/v1/audit/export", headers=admin.auth)

    assert [entry["seq"] for entry in page] == [3, 4, 5]
    assert page[0]["action"] == "chat.policy"
    assert page[0]["decision"]["kind"] == "policy"
    assert export.headers["content-type"] == "application/x-ndjson"
    assert "audit-export.jsonl" in export.headers["content-disposition"]
    report = verify_export(export.text.splitlines())
    assert report.ok
    assert report.entries == 6


async def test_the_fail_mode_is_read_and_changed_and_the_change_is_audited(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        before = (await client.get("/api/v1/audit/fail-mode", headers=admin.auth)).json()
        changed = await client.put(
            "/api/v1/audit/fail-mode", json={"mode": "open"}, headers=admin.auth
        )
        after = (await client.get("/api/v1/audit/fail-mode", headers=admin.auth)).json()
        invalid = await client.put(
            "/api/v1/audit/fail-mode", json={"mode": "maybe"}, headers=admin.auth
        )
        entries = (await client.get("/api/v1/audit/entries", headers=admin.auth)).json()

    assert (before, changed.json(), after) == (
        {"mode": "closed"},
        {"mode": "open"},
        {"mode": "open"},
    )
    assert invalid.status_code == 422
    assert [(entry["action"], entry["outcome"]) for entry in entries] == [
        ("audit.fail_mode.changed", "open")
    ]
