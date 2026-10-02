"""``arbiter demo`` end to end. Synchronous: the CLI runs its own event loop."""

import re

from tests.integration.test_cli_compliance import arbiter


def test_the_scenarios_are_listed_in_the_chosen_language() -> None:
    english = arbiter("demo", "list")
    italian = arbiter("demo", "list", "--locale", "it")

    assert re.search(r"first-inventory\s+A first inventory, before any review", english)
    assert re.search(r"shadow-ai\s+What the traffic shows and nobody declared", english)
    assert re.search(r"inventory-in-order\s+Un inventario tenuto in ordine", italian)
    assert "Every system and every request of a scenario is invented." in english
    assert "It does not provide legal advice." in english


def test_a_scenario_is_loaded_into_the_demo_tenant_and_compared_with_what_it_expects() -> None:
    arbiter("init")

    output = arbiter("demo", "run", "shadow-ai")
    again = arbiter("demo", "run", "shadow-ai", "--locale", "it")

    assert output.startswith("shadow-ai: What the traffic shows and nobody declared\n")
    assert re.search(
        r"web-shop-assistant\s+Transparency obligations\s+as the scenario expects", output
    )
    assert "      SCAN-PERSONAL-DATA-NOT-DECLARED\n" in output
    assert "      SCAN-RETIRED-SYSTEM-IN-USE\n" in output
    assert "Candidate systems named from the traffic: data-science, marketing-team" in output
    assert "DIFFERS" not in output
    assert "Loaded into the tenant 'demo'." in output
    assert re.search(r"legacy-faq-bot\s+Obblighi di trasparenza\s+come previsto", again)
    assert "DIVERSO" not in again


def test_the_demo_stays_in_its_own_tenant_and_can_be_looked_at_there() -> None:
    arbiter("init")
    arbiter("demo", "run", "--all")

    mine = arbiter("systems", "list")
    demo = arbiter("systems", "list", "--tenant", "demo")
    candidates = arbiter("systems", "discover", "--tenant", "demo")
    digest = arbiter("digest", "run", "--tenant", "demo")
    report = arbiter("report", "system", "cv-screening", "--tenant", "demo")

    assert "No AI system is declared." in mine
    assert "No candidate" in arbiter("systems", "discover")
    assert len(demo.strip().splitlines()) == 8
    assert "source:simulation:marketing-team" in candidates
    assert "8 declared systems" in digest
    assert "- **Review**: Confirmed by a reviewer" in report
    assert "No findings." in report


def test_a_demo_needs_one_scenario_or_all_and_a_name_that_exists() -> None:
    arbiter("init")

    assert "Error: name a scenario, or use --all" in arbiter("demo", "run", ok=False)
    assert "Error: name a scenario, or use --all" in arbiter(
        "demo", "run", "shadow-ai", "--all", ok=False
    )
    assert "Error: no scenario named 'nope' (available: first-inventory" in arbiter(
        "demo", "run", "nope", ok=False
    )
    assert "Error: " in arbiter("demo", "run", "--all", "--locale", "fr", ok=False)
