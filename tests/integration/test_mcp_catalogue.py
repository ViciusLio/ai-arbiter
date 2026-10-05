"""The MCP catalogue: servers, what they offer, and the allowlist (ADR-0048, ADR-0049)."""

from typing import Any
from uuid import UUID

import pytest

from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.errors import ConflictError, NotFoundError
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.gateway.identity.model import ScopeType
from ai_arbiter.gateway.mcp.catalogue import Caller, Governability, McpCatalogue, governability
from ai_arbiter.gateway.mcp.model import McpServer, McpTransport

URL = "https://tools.example.org/mcp"
PROJECT, OTHER_PROJECT, SYSTEM = new_id(), new_id(), new_id()


@pytest.fixture
def catalogue() -> McpCatalogue:
    return McpCatalogue(allow_http_hosts=["localhost"])


async def register(
    catalogue: McpCatalogue,
    database: Database,
    tenant_id: UUID,
    key: str = "files",
    **values: Any,
) -> McpServer:
    async with database.transaction() as session:
        return await catalogue.register(
            session,
            tenant_id,
            **{"key": key, "name": "File tools", "url": URL, **values},
        )


async def test_a_server_is_registered_listed_and_removed_with_what_hangs_on_it(
    catalogue: McpCatalogue, database: Database, tenant_id: UUID
) -> None:
    await register(catalogue, database, tenant_id)
    await register(catalogue, database, tenant_id, key="a-local", url="http://localhost:9000/mcp")
    async with database.transaction() as session:
        await catalogue.grant(
            session, tenant_id, "files", scope_type=ScopeType.TENANT, scope_id=None
        )
        server = await catalogue.get(session, tenant_id, "files")
        await catalogue.record_discovery(
            session, server, protocol_versions=["2026-07-28"], tools=["read", "write"]
        )

    async with database.transaction() as session:
        listed = [server.key for server in await catalogue.list(session, tenant_id)]
        await catalogue.remove(session, tenant_id, "files")
        left = [server.key for server in await catalogue.list(session, tenant_id)]
        grants = await catalogue.grants(session, tenant_id)

    assert listed == ["a-local", "files"]
    assert left == ["a-local"]
    assert grants == []
    async with database.session() as session:
        with pytest.raises(NotFoundError, match="no MCP server with the key 'files'"):
            await catalogue.get(session, tenant_id, "files")


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({"key": "Files"}, "lower-case letters"),
        ({"name": "  "}, "needs a name"),
        ({"url": None}, "needs its URL"),
        ({"url": "http://tools.example.org/mcp"}, "must use https"),
        ({"url": "https://user:pw@tools.example.org/mcp"}, "must hold no credentials"),
        ({"url": "https://tools.example.org/mcp#x"}, "no fragment"),
        ({"url": "file:///etc/passwd"}, "needs a host"),
        ({"credential": "plain-value"}, "credential: not a secret reference"),
        ({"transport": McpTransport.STDIO}, "only declared"),
    ],
)
async def test_a_server_that_cannot_be_governed_safely_is_refused(
    catalogue: McpCatalogue,
    database: Database,
    tenant_id: UUID,
    values: dict[str, Any],
    problem: str,
) -> None:
    with pytest.raises(ConflictError, match=problem):
        await register(catalogue, database, tenant_id, **values)


async def test_a_key_is_unique_in_a_tenant_and_free_in_another(
    catalogue: McpCatalogue, database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    await register(catalogue, database, tenant_id)
    await register(catalogue, database, other_tenant_id)

    with pytest.raises(ConflictError, match="already exists"):
        await register(catalogue, database, tenant_id)
    async with database.session() as session:
        mine = await catalogue.list(session, tenant_id)
        theirs = await catalogue.list(session, other_tenant_id)
    assert (len(mine), len(theirs)) == (1, 1)
    assert mine[0].id != theirs[0].id


async def test_a_server_is_governable_only_when_it_speaks_the_modern_revision(
    catalogue: McpCatalogue, database: Database, tenant_id: UUID
) -> None:
    http = await register(catalogue, database, tenant_id)
    stdio = await register(
        catalogue, database, tenant_id, key="local-git", url=None, transport=McpTransport.STDIO
    )
    states = [governability(http), governability(stdio)]

    async with database.transaction() as session:
        server = await catalogue.get(session, tenant_id, "files")
        await catalogue.record_discovery(
            session, server, protocol_versions=["2025-11-25", "2025-06-18"], tools=None
        )
        states.append(governability(server))
        await catalogue.record_discovery(
            session, server, protocol_versions=["2026-07-28", "2025-11-25"], tools=["read"]
        )
        states.append(governability(server))
        disabled = await catalogue.set_enabled(session, tenant_id, "files", False)
        states.append(governability(disabled))

    assert states == [
        Governability.NOT_ASKED,
        Governability.NOT_PROXIED,
        Governability.LEGACY_ONLY,
        Governability.GOVERNABLE,
        Governability.DISABLED,
    ]


async def test_a_discovery_replaces_the_list_of_tools_and_keeps_names_only(
    catalogue: McpCatalogue, database: Database, tenant_id: UUID
) -> None:
    await register(catalogue, database, tenant_id)

    async with database.transaction() as session:
        server = await catalogue.get(session, tenant_id, "files")
        await catalogue.record_discovery(
            session, server, protocol_versions=["2026-07-28"], tools=["read", "write", "read"]
        )
        first = list(await catalogue.tools(session, server))
        await catalogue.record_discovery(
            session, server, protocol_versions=["2026-07-28"], tools=["read", "search"]
        )
        second = list(await catalogue.tools(session, server))
        await catalogue.record_discovery(
            session, server, protocol_versions=["2026-07-28"], tools=None
        )
        untouched = list(await catalogue.tools(session, server))

    assert first == ["read", "write"]
    assert second == untouched == ["read", "search"]
    assert server.discovered_at is not None


async def test_nothing_is_allowed_until_a_grant_says_so(
    catalogue: McpCatalogue, database: Database, tenant_id: UUID
) -> None:
    server = await register(catalogue, database, tenant_id)
    project = Caller(tenant_id, PROJECT, None)
    other = Caller(tenant_id, OTHER_PROJECT, None)
    system = Caller(tenant_id, OTHER_PROJECT, SYSTEM)

    async with database.transaction() as session:
        before = await catalogue.allows(session, server, project, "read")
        await catalogue.grant(
            session, tenant_id, "files", scope_type=ScopeType.PROJECT, scope_id=PROJECT, tool="read"
        )
        again = await catalogue.grant(
            session, tenant_id, "files", scope_type=ScopeType.PROJECT, scope_id=PROJECT, tool="read"
        )
        await catalogue.grant(
            session, tenant_id, "files", scope_type=ScopeType.AI_SYSTEM, scope_id=SYSTEM
        )
        allowed = {
            "project reads": await catalogue.allows(session, server, project, "read"),
            "project writes": await catalogue.allows(session, server, project, "write"),
            "project lists": await catalogue.allows(session, server, project, None),
            "other project reads": await catalogue.allows(session, server, other, "read"),
            "other project lists": await catalogue.allows(session, server, other, None),
            "system writes": await catalogue.allows(session, server, system, "write"),
        }
        grants = await catalogue.grants(session, tenant_id, "files")

    assert before is False
    assert allowed == {
        "project reads": True,
        "project writes": False,
        "project lists": True,
        "other project reads": False,
        "other project lists": False,
        "system writes": True,
    }
    assert len(grants) == 2
    assert again.id in {grant.id for grant, _ in grants}


async def test_a_tenant_wide_grant_covers_every_caller_of_that_tenant_only(
    catalogue: McpCatalogue, database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    server = await register(catalogue, database, tenant_id)

    async with database.transaction() as session:
        grant = await catalogue.grant(
            session, tenant_id, "files", scope_type=ScopeType.TENANT, scope_id=None
        )
        mine = await catalogue.allows(session, server, Caller(tenant_id, None, None), "read")
        theirs = await catalogue.allows(
            session, server, Caller(other_tenant_id, PROJECT, None), "read"
        )
        with pytest.raises(NotFoundError):
            await catalogue.revoke(session, other_tenant_id, grant.id)
        await catalogue.revoke(session, tenant_id, grant.id)
        after = await catalogue.allows(session, server, Caller(tenant_id, None, None), "read")

    assert (mine, theirs, after) == (True, False, False)


async def test_grants_that_make_no_sense_are_refused(
    catalogue: McpCatalogue, database: Database, tenant_id: UUID
) -> None:
    await register(catalogue, database, tenant_id)

    async with database.transaction() as session:
        with pytest.raises(ConflictError, match="the tenant, a project or an AI system"):
            await catalogue.grant(
                session, tenant_id, "files", scope_type=ScopeType.TEAM, scope_id=new_id()
            )
        with pytest.raises(ConflictError, match="needs its id"):
            await catalogue.grant(
                session, tenant_id, "files", scope_type=ScopeType.PROJECT, scope_id=None
            )
        with pytest.raises(ConflictError, match="names one tool"):
            await catalogue.grant(
                session, tenant_id, "files", scope_type=ScopeType.TENANT, scope_id=None, tool=""
            )
        with pytest.raises(NotFoundError):
            await catalogue.grant(
                session, tenant_id, "nope", scope_type=ScopeType.TENANT, scope_id=None
            )
