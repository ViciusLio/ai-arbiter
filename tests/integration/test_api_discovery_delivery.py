"""Discovery and digest delivery over HTTP."""

import smtplib
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")

from sqlalchemy import select

from ai_arbiter.core.audit import AuditEntry
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.database import Database
from tests.api_support import app_for, issue_key, running
from tests.integration.test_api_compliance import EXAMPLES, declare, url_of

pytestmark = pytest.mark.usefixtures("gateway_secrets")

RECIPIENTS = [
    {"address": "ada@example.org", "locale": "it"},
    {"address": "grace@example.org"},
]


async def traffic(database: Database, tenant_id: UUID, count: int, **values: Any) -> None:
    async with database.transaction() as session:
        for _ in range(count):
            identifier = new_id()
            session.add(
                Interaction(
                    id=identifier,
                    tenant_id=tenant_id,
                    source_record_id=str(identifier),
                    started_at=utcnow() - timedelta(hours=1),
                    status="ok",
                    model="gpt-4o",
                    requested_model="gpt-4o",
                    provider="azure_openai",
                    **values,
                )
            )


async def test_candidates_are_listed_with_the_name_of_their_project_and_a_draft(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        auditor = await issue_key(app, tenant_id, AccessRole.AUDITOR)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        outsider = await issue_key(app, other_tenant_id, AccessRole.ADMIN)
        await traffic(database, tenant_id, 3, project_id=admin.project_id)
        await traffic(database, tenant_id, 2, source="litellm", source_group="sales")
        await traffic(database, tenant_id, 1, source="litellm")

        listed = await client.get("/api/v1/candidates", headers=auditor.auth)
        refused = await client.get("/api/v1/candidates", headers=developer.auth)
        elsewhere = await client.get("/api/v1/candidates", headers=outsider.auth)
        body = listed.json()
        draft = {**body["candidates"][0]["draft"], "name": "Assistant", **_roles()}
        declared = await client.put(
            f"/api/v1/systems/{draft['key']}", json=draft, headers=admin.auth
        )
        after = (await client.get("/api/v1/candidates", headers=admin.auth)).json()

    assert listed.status_code == 200
    assert (body["window_days"], body["ungrouped_requests"]) == (30, 1)
    project, source = body["candidates"]
    assert (project["kind"], project["requests"], project["models"]) == ("project", 3, ["gpt-4o"])
    assert project["reference"] == f"project:{admin.project_id}"
    assert project["project"].endswith(" / assistant")
    assert project["draft"]["project_ids"] == [str(admin.project_id)]
    assert project["draft"]["facts"] == {}
    assert (source["reference"], source["project"]) == ("source:litellm:sales", None)
    assert "proposal" in body["note"]
    assert refused.status_code == 403
    assert elsewhere.json()["candidates"] == []
    assert declared.status_code == 200, declared.text
    assert declared.json()["classification"]["tier"] == "undetermined"
    assert [item["reference"] for item in after["candidates"]] == ["source:litellm:sales"]


def _roles() -> dict[str, Any]:
    return {"roles": EXAMPLES["cv-screening"]["roles"]}


async def test_the_digest_is_delivered_through_the_configured_notifier(
    database: Database, tenant_id: UUID, tmp_path: Path
) -> None:
    app = app_for(
        url_of(database),
        notifications={
            "sender": "arbiter@example.org",
            "recipients": RECIPIENTS,
            "settings": {"directory": str(tmp_path / "outbox")},
        },
    )
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        auditor = await issue_key(app, tenant_id, AccessRole.AUDITOR)
        await declare(client, admin, "cv-screening")
        delivered = await client.post("/api/v1/digests/deliveries", headers=admin.auth)
        refused = await client.post("/api/v1/digests/deliveries", headers=auditor.auth)

    assert delivered.status_code == 200, delivered.text
    assert delivered.json() == {
        "sent": True,
        "notifier": "file",
        "messages": 2,
        "expected": 2,
        "recipients": 2,
        "error": None,
    }
    assert len(list((tmp_path / "outbox").glob("*.eml"))) == 2
    assert refused.status_code == 403
    async with database.session() as session:
        entry = (
            await session.scalars(select(AuditEntry).where(AuditEntry.action == "digest.sent"))
        ).one()
    assert entry.outcome == "messages:2/2"
    assert "example.org" not in str(entry.decision)


async def test_a_delivery_that_cannot_start_says_what_to_fix(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        response = await client.post("/api/v1/digests/deliveries", headers=admin.auth)

    assert response.status_code == 409
    assert "notifications.sender" in response.json()["detail"]


async def test_a_delivery_the_server_refuses_answers_502_and_is_audited(
    database: Database, tenant_id: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*arguments: Any, **options: Any) -> None:
        raise ConnectionRefusedError

    monkeypatch.setattr(smtplib, "SMTP", refuse)
    app = app_for(
        url_of(database),
        plugins={"notifier": "smtp"},
        notifications={
            "sender": "arbiter@example.org",
            "recipients": RECIPIENTS,
            "settings": {"host": "mail.example.org", "security": "none"},
        },
    )
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        response = await client.post("/api/v1/digests/deliveries", headers=admin.auth)

    assert response.status_code == 502
    assert response.json() == {
        "sent": False,
        "notifier": "smtp",
        "messages": 0,
        "expected": 2,
        "recipients": 0,
        "error": "ConnectionRefusedError",
    }
    async with database.session() as session:
        actions = (await session.scalars(select(AuditEntry.action))).all()
    assert "digest.send_failed" in actions
