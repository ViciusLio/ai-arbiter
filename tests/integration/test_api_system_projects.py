"""A key that belongs to a system through its project, at the gateway (ADR-0059)."""

from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")

from sqlalchemy import select

from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.database import Database
from tests.api_support import app_for, issue_key, running
from tests.integration.test_api_compliance import CHAT, url_of
from tests.integration.test_api_compliance import declare as declare_over_http

pytestmark = pytest.mark.usefixtures("gateway_secrets")


async def recorded(database: Database, project_id: UUID) -> list[tuple[str, UUID | None]]:
    async with database.session() as session:
        rows = await session.execute(
            select(Interaction.status, Interaction.ai_system_id)
            .where(Interaction.project_id == project_id)
            .order_by(Interaction.started_at, Interaction.id)
        )
        return [(status, system_id) for status, system_id in rows]


async def test_a_key_tied_to_no_system_belongs_to_the_one_system_that_names_its_project(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        worker = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        before = await client.post("/v1/chat/completions", json=CHAT, headers=worker.auth)
        system = await declare_over_http(
            client, admin, "call-centre-mood-monitor", project_ids=[str(worker.project_id)]
        )
        after = await client.post("/v1/chat/completions", json=CHAT, headers=worker.auth)

    assert before.status_code == 200
    assert after.status_code == 403
    assert after.json()["reasons"][0]["rule_id"] == "POL-SYSTEM-PROHIBITED"
    assert await recorded(database, worker.project_id) == [
        ("ok", None),
        ("denied", UUID(system["id"])),
    ]


async def test_a_project_named_by_two_systems_gives_its_keys_no_system(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        worker = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        shared = [str(worker.project_id)]
        await declare_over_http(client, admin, "call-centre-mood-monitor", project_ids=shared)
        await declare_over_http(client, admin, "invoice-data-extraction", project_ids=shared)
        answered = await client.post("/v1/chat/completions", json=CHAT, headers=worker.auth)

    # Which of the two the request belongs to would be a guess: it belongs to neither,
    # and the tier of neither is applied.
    assert answered.status_code == 200
    assert await recorded(database, worker.project_id) == [("ok", None)]
