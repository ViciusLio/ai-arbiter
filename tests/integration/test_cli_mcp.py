"""``arbiter mcp`` end to end. Synchronous: the CLI runs its own event loop."""

import re

import pytest

from tests.integration.test_cli_compliance import arbiter, workspace

URL = "https://tools.example.org/mcp"


def test_a_server_is_registered_listed_and_removed() -> None:
    arbiter("init")

    empty = arbiter("mcp", "servers", "list")
    added = arbiter("mcp", "servers", "add", "files", "--name", "File tools", "--url", URL)
    arbiter("mcp", "servers", "add", "local-git", "--name", "Git", "--stdio")
    listed = arbiter("mcp", "servers", "list")
    removed = arbiter("mcp", "servers", "remove", "local-git")

    assert "No MCP server is registered." in empty
    assert "Registered 'files' (not_asked)." in added
    assert "No one may call it yet: arbiter mcp grants add files" in added
    assert re.search(rf"files\s+not_asked\s+streamable_http\s+0 tools\s+{re.escape(URL)}", listed)
    assert re.search(r"local-git\s+not_proxied\s+stdio\s+0 tools\s+-", listed)
    assert "Removed 'local-git'." in removed
    assert "local-git" not in arbiter("mcp", "servers", "list")
    audit = arbiter("report", "audit")
    assert "| `mcp_server.registered` |" in audit
    assert "| `mcp_server.removed` |" in audit


def test_grants_are_given_to_the_tenant_or_a_system_and_withdrawn() -> None:
    workspace()
    arbiter("mcp", "servers", "add", "files", "--name", "File tools", "--url", URL)

    nobody = arbiter("mcp", "grants", "list")
    everyone = arbiter("mcp", "grants", "add", "files")
    system = arbiter("mcp", "grants", "add", "files", "--system", "cv-screening", "--tool", "read")
    listed = arbiter("mcp", "grants", "list", "files")
    withdrawn = arbiter("mcp", "grants", "remove", everyone.split()[0])

    assert "No grant: nobody may call an MCP server through the proxy." in nobody
    assert "tenant may call every tool of 'files'." in everyone
    assert "ai_system may call the tool 'read' of 'files'." in system
    assert len(listed.strip().splitlines()) == 2
    assert withdrawn.startswith("Withdrew grant ")
    assert len(arbiter("mcp", "grants", "list").strip().splitlines()) == 1


def test_what_the_catalogue_cannot_accept_is_refused_with_a_reason() -> None:
    workspace()
    arbiter("mcp", "servers", "add", "files", "--name", "File tools", "--url", URL)

    def refused(*arguments: str) -> str:
        return arbiter("mcp", *arguments, ok=False)

    assert "Error: an MCP server with the key 'files' already exists" in refused(
        "servers", "add", "files", "--name", "Again", "--url", URL
    )
    assert "Error: the URL of a server must use https" in refused(
        "servers", "add", "plain", "--name", "Plain", "--url", "http://tools.example.org/mcp"
    )
    assert "Error: a stdio server is only declared" in refused(
        "servers", "add", "local", "--name", "Local", "--stdio", "--url", URL
    )
    assert "Error: credential: not a secret reference" in refused(
        "servers", "add", "keyed", "--name", "Keyed", "--url", URL, "--credential", "value"
    )
    assert "Error: no system with key 'nope'" in refused(
        "servers", "add", "owned", "--name", "Owned", "--url", URL, "--system", "nope"
    )
    assert "Error: no MCP server with the key 'nope'" in refused("grants", "add", "nope")
    assert "Error: use either --project or --system" in refused(
        "grants",
        "add",
        "files",
        "--system",
        "cv-screening",
        "--project",
        "00000000-0000-0000-0000-000000000000",
    )
    assert "Error: no grant with the id 'zzz'" in refused("grants", "remove", "zzz")


def test_plain_http_is_accepted_only_for_the_hosts_the_configuration_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arbiter("init")
    monkeypatch.setenv("ARBITER_MCP__ALLOW_HTTP_HOSTS", '["mock-mcp"]')

    added = arbiter(
        "mcp", "servers", "add", "mock", "--name", "Mock", "--url", "http://mock-mcp:9000/mcp"
    )
    refused = arbiter(
        "mcp",
        "servers",
        "add",
        "other",
        "--name",
        "Other",
        "--url",
        "http://other:9000/mcp",
        ok=False,
    )

    assert "Registered 'mock'" in added
    assert "Error: the URL of a server must use https" in refused


def test_refresh_asks_the_server_and_stores_what_it_says(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("httpx", reason="needs the gateway extra")
    pytest.importorskip("mcp_types", reason="needs the mcp extra")
    from functools import partial

    from ai_arbiter.cli import mcp as mcp_cli
    from ai_arbiter.gateway.mcp.proxy import McpProxy
    from tests.mcp_support import FakeMcpServer

    server = FakeMcpServer(tools=("search", "read"))
    monkeypatch.setattr(mcp_cli, "McpProxy", partial(McpProxy, transport=server.transport))
    arbiter("init")
    arbiter("mcp", "servers", "add", "files", "--name", "File tools", "--url", URL)
    arbiter("mcp", "servers", "add", "local-git", "--name", "Git", "--stdio")

    refreshed = arbiter("mcp", "servers", "refresh", "files")
    listed = arbiter("mcp", "servers", "list")

    assert "'files' is governable. Revisions: 2026-07-28." in refreshed
    assert "Tools: read, search" in refreshed
    assert re.search(r"files\s+governable\s+streamable_http\s+2 tools", listed)
    assert "Error: the server 'local-git' is not_proxied" in arbiter(
        "mcp", "servers", "refresh", "local-git", ok=False
    )
    assert "| `mcp_server.discovered` |" in arbiter("report", "audit")
