"""``arbiter a2a`` end to end. Synchronous: the CLI runs its own event loop."""

import json
import re
from functools import partial

import pytest

from tests.integration.test_cli_compliance import arbiter, workspace

CARD_URL = "https://agent.example.org/.well-known/agent-card.json"


def test_an_agent_is_registered_listed_and_removed() -> None:
    arbiter("init")

    empty = arbiter("a2a", "agents", "list")
    added = arbiter(
        "a2a", "agents", "add", "routes", "--name", "Route planner", "--card-url", CARD_URL
    )
    listed = arbiter("a2a", "agents", "list")
    removed = arbiter("a2a", "agents", "remove", "routes")

    assert "No agent is registered." in empty
    assert "Its card was not read yet: arbiter a2a agents refresh routes" in added
    assert "No one may call it yet: arbiter a2a grants add routes" in added
    assert re.search(r"routes\s+not_fetched\s+not_fetched\s+-", listed)
    assert "Removed 'routes'." in removed
    audit = arbiter("report", "audit")
    assert "| `a2a_agent.registered` |" in audit
    assert "| `a2a_agent.removed` |" in audit


def test_grants_are_given_and_withdrawn_by_the_short_id_shown() -> None:
    workspace()
    arbiter("a2a", "agents", "add", "routes", "--name", "Route planner", "--card-url", CARD_URL)

    nobody = arbiter("a2a", "grants", "list")
    everyone = arbiter("a2a", "grants", "add", "routes")
    system = arbiter("a2a", "grants", "add", "routes", "--system", "cv-screening")
    listed = arbiter("a2a", "grants", "list", "routes")
    withdrawn = arbiter("a2a", "grants", "remove", everyone.split()[0])

    assert "No grant: nobody may call an agent of the registry." in nobody
    assert "tenant may call 'routes'." in everyone
    assert "ai_system may call 'routes'." in system
    assert len(listed.strip().splitlines()) == 2
    assert withdrawn.startswith("Withdrew grant ")
    assert len(arbiter("a2a", "grants", "list").strip().splitlines()) == 1


def test_what_the_registry_cannot_accept_is_refused_with_a_reason() -> None:
    workspace()
    arbiter("a2a", "agents", "add", "routes", "--name", "Route planner", "--card-url", CARD_URL)

    def refused(*arguments: str) -> str:
        return arbiter("a2a", *arguments, ok=False)

    assert "Error: an agent with the key 'routes' already exists" in refused(
        "agents", "add", "routes", "--name", "Again", "--card-url", CARD_URL
    )
    assert "Error: the URL of an Agent Card must use https" in refused(
        "agents", "add", "plain", "--name", "Plain", "--card-url", "http://agent.example.org/c.json"
    )
    assert "Error: credential: not a secret reference" in refused(
        "agents", "add", "keyed", "--name", "K", "--card-url", CARD_URL, "--credential", "value"
    )
    assert "Error: no system with key 'nope'" in refused(
        "agents", "add", "owned", "--name", "O", "--card-url", CARD_URL, "--system", "nope"
    )
    assert "Error: no agent with the key 'nope'" in refused("grants", "add", "nope")
    assert "Error: no grant with the id 'zzz'" in refused("grants", "remove", "zzz")


def test_refresh_reads_the_card_and_says_whether_a_trusted_key_signed_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    httpx = pytest.importorskip("httpx", reason="needs the gateway extra")
    pytest.importorskip("a2a", reason="needs the a2a extra")
    from ai_arbiter.cli import a2a as a2a_cli
    from ai_arbiter.gateway.a2a.registry import A2aRegistry
    from tests.a2a_support import CARD, SigningKey

    key = SigningKey()
    document = key.sign(CARD)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=document))
    monkeypatch.setattr(a2a_cli, "A2aRegistry", partial(A2aRegistry, transport=transport))
    arbiter("init")
    arbiter("a2a", "agents", "add", "routes", "--name", "Route planner", "--card-url", CARD_URL)

    untrusted = arbiter("a2a", "agents", "refresh", "routes")
    monkeypatch.setenv("ARBITER_A2A__TRUSTED_KEYS", json.dumps([{"kid": key.kid, "jwk": key.jwk}]))
    trusted = arbiter("a2a", "agents", "refresh", "routes")
    listed = arbiter("a2a", "agents", "list")

    assert "'routes': the card is unknown_key; the agent is governable." in untrusted
    assert (
        "'routes': the card is verified with the key 'key-1'; the agent is governable." in trusted
    )
    assert "Interfaces a proxy can forward to: 2" in trusted
    assert re.search(r"routes\s+governable\s+verified\s+Route planner", listed)
    assert "| `a2a_agent.card_read` |" in arbiter("report", "audit")
