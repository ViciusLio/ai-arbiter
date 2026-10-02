from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")

import httpx
from sqlalchemy import select

from ai_arbiter.compliance.inventory.declarations import load_declarations
from ai_arbiter.core.audit import AuditEntry
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.persistence.database import Database
from tests.api_support import MOCK, Issued, app_for, issue_key, running

pytestmark = pytest.mark.usefixtures("gateway_secrets")

EXAMPLES = {
    system.key: system.model_dump(mode="json", exclude={"use"})
    for system in load_declarations(Path(__file__).parents[2] / "examples" / "systems.yaml")
}
CHAT = {"model": "gpt-test", "messages": [{"role": "user", "content": "Hello"}]}


def url_of(database: Database) -> str:
    return database.engine.url.render_as_string(False)


async def declare(
    client: httpx.AsyncClient, admin: Issued, key: str, **changes: Any
) -> dict[str, Any]:
    body = {**EXAMPLES[key], **changes}
    response = await client.put(f"/api/v1/systems/{key}", json=body, headers=admin.auth)
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_a_system_is_declared_classified_and_explained(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        system = await declare(client, admin, "cv-screening")
        again = await declare(client, admin, "cv-screening")
        listed = (await client.get("/api/v1/systems", headers=admin.auth)).json()
        fetched = (await client.get("/api/v1/systems/cv-screening", headers=admin.auth)).json()

    classification = system["classification"]
    assert (system["key"], system["roles"]) == ("cv-screening", ["deployer"])
    assert (classification["tier"], classification["status"]) == ("high_risk", "proposed")
    assert classification["rulepack_review"] == "pending"
    assert "Indicative" in classification["note"]
    recruitment = classification["obligations"][1]
    assert recruitment == {
        "id": "AIA-ANNEX3-4A-RECRUITMENT",
        "outcome": "high_risk",
        "text": "High-risk: recruitment or selection of persons (Annex III(4)(a)).",
        "legal_refs": ["6(2)", "Annex III(4)(a)"],
        "roles": [],
        "applies_from": "2027-12-02",
        "applicable": False,
        "applies_to_declared_roles": True,
    }
    assert classification["obligations"][0]["applicable"] is True
    assert again["classification"]["id"] == classification["id"]
    assert [item["key"] for item in listed] == ["cv-screening"]
    assert fetched == again


async def test_texts_follow_the_language_of_the_request(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await declare(client, admin, "marketing-copy-generator")
        italian = {**admin.auth, "Accept-Language": "it"}
        system = (
            await client.get("/api/v1/systems/marketing-copy-generator", headers=italian)
        ).json()
        questions = (
            await client.get("/api/v1/systems/marketing-copy-generator/questions", headers=italian)
        ).json()

    assert system["classification"]["tier"] == "undetermined"
    assert system["classification"]["missing_facts"][0] == "prohibited.manipulative_techniques"
    assert questions[0]["fact"] == "prohibited.manipulative_techniques"
    assert questions[0]["question"].startswith("Utilizza tecniche subliminali")
    assert (questions[0]["stage"], questions[0]["reference"]) == ("prohibited", "Art. 5(1)(a)")
    assert "annex3.employment_recruitment" not in [item["fact"] for item in questions]


async def test_a_classification_is_reviewed_under_the_principal_of_the_key(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await declare(client, admin, "loan-pre-screening")
        confirmed = await client.post(
            "/api/v1/systems/loan-pre-screening/review",
            json={"decision": "confirmed"},
            headers=admin.auth,
        )
        no_reason = await client.post(
            "/api/v1/systems/loan-pre-screening/review",
            json={"decision": "overridden", "tier": "high_risk"},
            headers=admin.auth,
        )
        overridden = await client.post(
            "/api/v1/systems/loan-pre-screening/review",
            json={
                "decision": "overridden",
                "tier": "high_risk",
                "reason": "The provider's assessment does not cover our use.",
            },
            headers=admin.auth,
        )

    assert confirmed.json()["classification"]["status"] == "confirmed"
    assert confirmed.json()["classification"]["reviewed_by"] == str(admin.principal_id)
    assert (no_reason.status_code, no_reason.json()["code"]) == (409, "conflict")
    result = overridden.json()["classification"]
    assert (result["tier"], result["engine_tier"], result["status"]) == (
        "high_risk",
        "minimal",
        "overridden",
    )


async def test_invalid_declarations_are_refused(database: Database, tenant_id: UUID) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        mismatch = await client.put(
            "/api/v1/systems/other-key", json=EXAMPLES["cv-screening"], headers=admin.auth
        )
        unknown_fact = await client.put(
            "/api/v1/systems/cv-screening",
            json={**EXAMPLES["cv-screening"], "facts": {"annex3.employement": True}},
            headers=admin.auth,
        )
        bad_role = await client.put(
            "/api/v1/systems/x",
            json={"key": "x", "name": "X", "roles": [{"role": "owner"}]},
            headers=admin.auth,
        )
        missing = await client.get("/api/v1/systems/nope", headers=admin.auth)

    assert (mismatch.status_code, unknown_fact.status_code) == (409, 409)
    assert "unknown facts: annex3.employement" in unknown_fact.json()["detail"]
    assert bad_role.status_code == 422
    assert missing.status_code == 404


async def test_scan_then_findings_are_reviewed_through_the_api(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        for key in ("cv-screening", "loan-pre-screening"):
            await declare(client, admin, key)
        scan = await client.post("/api/v1/scans", headers=admin.auth)
        findings = (await client.get("/api/v1/findings", headers=admin.auth)).json()
        target = next(f for f in findings if f["rule_id"] == "SCAN-DEROGATION-WITHOUT-ASSESSMENT")
        detail = (await client.get(f"/api/v1/findings/{target['id']}", headers=admin.auth)).json()
        confirmed = await client.post(
            f"/api/v1/findings/{target['id']}/transitions",
            json={"to": "confirmed"},
            headers=admin.auth,
        )
        refused = await client.post(
            f"/api/v1/findings/{target['id']}/transitions",
            json={"to": "false_positive", "reason": "It is not a real problem."},
            headers=admin.auth,
        )
        only_confirmed = (
            await client.get("/api/v1/findings", params={"status": "confirmed"}, headers=admin.auth)
        ).json()

    assert scan.status_code == 201
    assert scan.json()["stats"]["systems"] == 2
    assert target["severity"] == "medium"
    assert target["text"].startswith("The Article 6(3) derogation is claimed")
    assert target["legal_refs"] == [{"regulation": "EU-AI-ACT", "article": "6(4)"}]
    assert detail["evidence"][0]["system_key"] == "loan-pre-screening"
    assert "Indicative" in detail["note"]
    assert confirmed.json()["status"] == "confirmed"
    assert (refused.status_code, refused.json()["code"]) == (409, "conflict")
    assert [item["id"] for item in only_confirmed] == [target["id"]]


async def test_suppressions_are_created_listed_and_removed(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await declare(client, admin, "cv-screening")
        created = await client.post(
            "/api/v1/suppressions",
            json={
                "rule_id": "SCAN-SYSTEM-WITHOUT-OWNER",
                "reason": "Owners are tracked elsewhere.",
            },
            headers=admin.auth,
        )
        scan = (await client.post("/api/v1/scans", headers=admin.auth)).json()
        listed = (await client.get("/api/v1/suppressions", headers=admin.auth)).json()
        removed = await client.delete(
            f"/api/v1/suppressions/{created.json()['id']}", headers=admin.auth
        )
        short_reason = await client.post(
            "/api/v1/suppressions", json={"rule_id": "X", "reason": "no"}, headers=admin.auth
        )

    assert created.status_code == 201
    assert scan["stats"]["suppressed"] == 1
    assert [item["rule_id"] for item in listed] == ["SCAN-SYSTEM-WITHOUT-OWNER"]
    assert listed[0]["created_by"] == str(admin.principal_id)
    assert removed.status_code == 204
    assert short_reason.status_code == 409


async def test_the_digest_is_served_as_markdown_or_html(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await declare(client, admin, "cv-screening")
        await client.post("/api/v1/scans", headers=admin.auth)
        markdown = await client.post("/api/v1/digests", headers=admin.auth)
        html = await client.post(
            "/api/v1/digests", params={"format": "html", "locale": "it"}, headers=admin.auth
        )
        unsupported = await client.post(
            "/api/v1/digests", params={"locale": "fr"}, headers=admin.auth
        )

    assert markdown.headers["content-type"] == "text/markdown; charset=utf-8"
    assert markdown.text.startswith("# Daily digest")
    assert "| CV screening (`cv-screening`) | High-risk |" in markdown.text
    assert html.headers["content-type"] == "text/html; charset=utf-8"
    assert "<h1>Digest giornaliero</h1>" in html.text
    assert unsupported.status_code == 409


async def test_only_an_admin_changes_the_inventory_and_an_auditor_reads_it(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        auditor = await issue_key(app, tenant_id, AccessRole.AUDITOR)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        await declare(client, admin, "cv-screening")

        async def code(method: str, path: str, key: Issued, **kwargs: Any) -> int:
            return (
                await client.request(method, f"/api/v1{path}", headers=key.auth, **kwargs)
            ).status_code

        auditor_codes = [
            await code("GET", "/systems", auditor),
            await code("GET", "/systems/cv-screening/questions", auditor),
            await code("GET", "/findings", auditor),
            await code("POST", "/digests", auditor),
            await code("PUT", "/systems/cv-screening", auditor, json=EXAMPLES["cv-screening"]),
            await code("POST", "/scans", auditor),
            await code(
                "POST", "/systems/cv-screening/review", auditor, json={"decision": "confirmed"}
            ),
        ]
        developer_codes = [
            await code("GET", "/systems", developer),
            await code("GET", "/findings", developer),
        ]

    assert auditor_codes == [200, 200, 200, 200, 403, 403, 403]
    assert developer_codes == [403, 403]


async def test_the_inventory_of_one_tenant_is_invisible_to_another(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        mine = await issue_key(app, tenant_id, AccessRole.ADMIN)
        theirs = await issue_key(app, other_tenant_id, AccessRole.ADMIN)
        await declare(client, mine, "cv-screening")
        await client.post("/api/v1/scans", headers=mine.auth)
        finding = (await client.get("/api/v1/findings", headers=mine.auth)).json()[0]

        systems = (await client.get("/api/v1/systems", headers=theirs.auth)).json()
        findings = (await client.get("/api/v1/findings", headers=theirs.auth)).json()
        system = await client.get("/api/v1/systems/cv-screening", headers=theirs.auth)
        other_finding = await client.get(f"/api/v1/findings/{finding['id']}", headers=theirs.auth)

    assert (systems, findings) == ([], [])
    assert (system.status_code, other_finding.status_code) == (404, 404)


async def key_for_system(
    app: Any, client: httpx.AsyncClient, tenant_id: UUID, admin: Issued, key: str
) -> Issued:
    system = await declare(client, admin, key)
    return await issue_key(app, tenant_id, AccessRole.DEVELOPER, ai_system_id=UUID(system["id"]))


async def test_a_system_classified_as_prohibited_gets_no_model(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        prohibited = await key_for_system(app, client, tenant_id, admin, "call-centre-mood-monitor")
        minimal = await key_for_system(app, client, tenant_id, admin, "invoice-data-extraction")
        denied = await client.post("/v1/chat/completions", json=CHAT, headers=prohibited.auth)
        allowed = await client.post("/v1/chat/completions", json=CHAT, headers=minimal.auth)
        unattributed = await client.post("/v1/chat/completions", json=CHAT, headers=admin.auth)

    assert denied.status_code == 403
    reason = denied.json()["reasons"][0]
    assert reason["rule_id"] == "POL-SYSTEM-PROHIBITED"
    assert reason["legal_refs"] == [{"regulation": "EU-AI-ACT", "article": "5"}]
    assert "indicative" in reason["message"]
    assert (allowed.status_code, unattributed.status_code) == (200, 200)


async def test_requests_of_a_high_risk_system_are_routed_only_where_its_tier_allows(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(
        url_of(database),
        {**MOCK, "name": "us", "priority": 1, "region": "eastus"},
        {**MOCK, "name": "eu", "priority": 2, "region": "westeurope"},
        router={
            "retries": 0,
            "retry_backoff_ms": 0,
            "constraints": {"high_risk": {"allowed_regions": ["westeurope"]}},
        },
    )
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        high_risk = await key_for_system(app, client, tenant_id, admin, "cv-screening")
        minimal = await key_for_system(app, client, tenant_id, admin, "invoice-data-extraction")
        constrained = await client.post("/v1/chat/completions", json=CHAT, headers=high_risk.auth)
        free = await client.post("/v1/chat/completions", json=CHAT, headers=minimal.auth)

    assert (constrained.status_code, free.status_code) == (200, 200)
    async with database.session() as session:
        routing = (
            await session.scalars(
                select(AuditEntry)
                .where(AuditEntry.action == "chat.routing")
                .order_by(AuditEntry.seq)
            )
        ).all()
    assert [entry.outcome for entry in routing] == ["route:eu", "route:us"]
    assert routing[0].decision is not None
    candidates = {c["deployment"]: c for c in routing[0].decision["details"]["candidates"]}
    assert candidates["us"]["selected"] is False
    assert candidates["us"]["reason"] == "not allowed for the risk tier high_risk"


async def test_when_the_tier_allows_no_deployment_the_request_is_refused_with_the_reason(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(
        url_of(database),
        router={"constraints": {"high_risk": {"allowed_deployments": ["somewhere-else"]}}},
    )
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        high_risk = await key_for_system(app, client, tenant_id, admin, "cv-screening")
        response = await client.post("/v1/chat/completions", json=CHAT, headers=high_risk.auth)

    assert response.status_code == 404
    assert "not allowed for the risk tier high_risk" in response.json()["detail"]


async def test_the_openapi_document_lists_the_compliance_endpoints(database: Database) -> None:
    async with running(app_for(url_of(database))) as client:
        document = (await client.get("/openapi.json")).json()

    assert {
        "/api/v1/systems",
        "/api/v1/systems/{key}",
        "/api/v1/systems/{key}/questions",
        "/api/v1/systems/{key}/review",
        "/api/v1/scans",
        "/api/v1/findings",
        "/api/v1/findings/{finding_id}/transitions",
        "/api/v1/suppressions",
        "/api/v1/digests",
    } <= set(document["paths"])
    for path, operations in document["paths"].items():
        for operation in operations.values():
            assert operation.get("summary"), path
