from uuid import UUID

import pytest

pytest.importorskip("fastapi", reason="needs the gateway extra")

from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.persistence.database import Database
from tests.api_support import app_for, issue_key, running
from tests.integration.test_api_compliance import declare, url_of

pytestmark = pytest.mark.usefixtures("gateway_secrets")


async def test_a_system_report_is_served_as_markdown_or_html(
    database: Database, tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        await declare(client, admin, "cv-screening")
        path = "/api/v1/systems/cv-screening/report"
        markdown = await client.get(path, headers=admin.auth)
        html = await client.get(path, params={"format": "html", "locale": "it"}, headers=admin.auth)
        unsupported = await client.get(path, params={"locale": "fr"}, headers=admin.auth)
        unknown = await client.get("/api/v1/systems/no-such-system/report", headers=admin.auth)

    assert markdown.headers["content-type"] == "text/markdown; charset=utf-8"
    assert markdown.text.startswith("# System report: CV screening")
    assert "- **Tier**: High-risk" in markdown.text
    assert html.headers["content-type"] == "text/html; charset=utf-8"
    assert "<h1>Report di sistema: CV screening</h1>" in html.text
    assert unsupported.status_code == 409
    assert unknown.status_code == 404


async def test_an_audit_report_is_served_to_an_auditor_and_not_to_a_developer(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    app = app_for(url_of(database))
    async with running(app) as client:
        admin = await issue_key(app, tenant_id, AccessRole.ADMIN)
        auditor = await issue_key(app, tenant_id, AccessRole.AUDITOR)
        developer = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        outsider = await issue_key(app, other_tenant_id, AccessRole.AUDITOR)
        await declare(client, admin, "cv-screening")
        report = await client.get("/api/v1/audit/report", headers=auditor.auth)
        html = await client.get(
            "/api/v1/audit/report", params={"format": "html", "days": 7}, headers=auditor.auth
        )
        refused = await client.get("/api/v1/audit/report", headers=developer.auth)
        system_refused = await client.get(
            "/api/v1/systems/cv-screening/report", headers=developer.auth
        )
        elsewhere = await client.get("/api/v1/audit/report", headers=outsider.auth)

    assert report.headers["content-type"] == "text/markdown; charset=utf-8"
    assert report.text.startswith("# Audit report")
    assert "no broken link" in report.text
    assert "| `system.declared` |" in report.text
    assert "<h1>Audit report</h1>" in html.text
    assert (refused.status_code, system_refused.status_code) == (403, 403)
    assert "`system.declared`" not in elsewhere.text
