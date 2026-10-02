"""Helpers for tests that go through the HTTP application. Needs the gateway extra."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from fastapi import FastAPI

from ai_arbiter.core.config import Settings, load_settings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.gateway.api.app import create_app
from ai_arbiter.gateway.identity.model import PrincipalKind
from ai_arbiter.gateway.runtime import GatewayRuntime

MOCK = {"name": "mock", "provider": "mock", "model": "mock-small", "serves": ["gpt-test"]}
ECHO = {**MOCK, "settings": {"echo": True}}


@asynccontextmanager
async def running(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Run the application lifespan and yield a client bound to it."""
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://arbiter.test") as client,
    ):
        yield client


def gateway_settings(url: str, *deployments: dict[str, Any], **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database": {"url": url},
        "deployments": list(deployments or (MOCK,)),
        "redaction": {"key": "secret://redaction-key"},
        "router": {"retry_backoff_ms": 0, "retries": 0},
        **overrides,
    }
    return load_settings(**values)


@dataclass
class Issued:
    key: str
    key_id: str
    project_id: UUID
    team_id: UUID
    principal_id: UUID

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key}"}


async def issue_key(
    app: FastAPI, tenant_id: UUID, *roles: AccessRole, ai_system_id: UUID | None = None
) -> Issued:
    """Create a team, a project and a service principal with ``roles``, and a key for it."""
    runtime: GatewayRuntime = app.state.runtime
    async with runtime.database.transaction() as session:
        team = await runtime.identity.create_team(session, tenant_id, f"team-{new_id()}")
        project = await runtime.identity.create_project(session, tenant_id, team.id, "assistant")
        principal = await runtime.identity.create_principal(
            session, tenant_id, kind=PrincipalKind.SERVICE, display_name="Backend of Ada Lovelace"
        )
        for role in roles:
            await runtime.identity.grant_role(
                session, tenant_id, principal_id=principal.id, role=role
            )
        row, key = await runtime.identity.issue_api_key(
            session,
            tenant_id,
            project_id=project.id,
            principal_id=principal.id,
            name="test key",
            ai_system_id=ai_system_id,
        )
    return Issued(key, row.key_id, project.id, team.id, principal.id)


def app_for(url: str, *deployments: dict[str, Any], **overrides: Any) -> FastAPI:
    return create_app(gateway_settings(url, *deployments, **overrides))
