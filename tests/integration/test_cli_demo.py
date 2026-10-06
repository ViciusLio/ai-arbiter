"""``arbiter demo`` end to end. Synchronous: the CLI runs its own event loop."""

import re
from pathlib import Path

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


def test_the_tour_shows_the_gateway_and_the_toolkit_at_work_and_can_be_repeated() -> None:
    import pytest

    pytest.importorskip("fastapi", reason="needs the gateway extra")
    pytest.importorskip("mcp_types", reason="needs the mcp extra")
    pytest.importorskip("a2a", reason="needs the a2a extra")
    arbiter("init")

    output = arbiter("demo", "tour")
    again = arbiter("demo", "tour", "--locale", "it")

    assert "DIFFERS" not in output
    assert output.count("[as the scenario expects]") == 7
    assert "10 invented systems were declared, classified and scanned." in output
    assert "Categories masked before the model saw the prompt: email." in output
    assert "was denied by the rule POL-SYSTEM-PROHIBITED." in output
    assert "listed the tools read, write." in output
    assert "calling another was denied by MCP-CALL-NOT-GRANTED." in output
    assert "The card of the agent was verified and the call went through." in output
    assert "it was invalid, and the call was denied by A2A-CARD-NOT-TRUSTED." in output
    assert "no broken link" in output
    assert "It does not provide legal advice." in output
    assert "DIVERSO" not in again
    assert again.count("[come previsto dallo scenario]") == 7
    # Nothing of the demonstration is in the tenant of the organisation.
    assert "No AI system is declared." in arbiter("systems", "list")
    assert "No MCP server is registered." in arbiter("mcp", "servers", "list")
    listed = arbiter("mcp", "servers", "list", "--tenant", "demo")
    assert re.search(r"demo-files\s+governable\s+streamable_http\s+2 tools", listed)
    assert re.search(
        r"demo-routes\s+governable\s+verified", arbiter("a2a", "agents", "list", "--tenant", "demo")
    )


def test_the_consulting_case_follows_a_firm_that_approved_one_family_of_models(
    tmp_path: Path,
) -> None:
    import pytest

    pytest.importorskip("fastapi", reason="needs the gateway extra")
    pytest.importorskip("mcp_types", reason="needs the mcp extra")
    arbiter("init")
    page = tmp_path / "out" / "demo.html"

    output = arbiter("demo", "tour", "--case", "consulting", "--report", str(page))
    first = page.read_text(encoding="utf-8")
    again = arbiter("demo", "tour", "--case", "consulting", "--locale", "it", "--report", str(page))
    second = page.read_text(encoding="utf-8")

    assert "DIFFERS" not in output
    assert output.count("[as the scenario expects]") == 13
    assert "coding-ide: Minimal" in output
    assert "cv-screening: High-risk" in output
    assert "Approved models: claude-sonnet-5-5, claude-haiku-4-5." in output
    assert "set to claude-sonnet-5-5" in output
    assert "masked before the model saw the prompt: email, iban." in output
    assert "switched the coding IDE to gpt-4o." in output
    assert "the model is not approved: denied by POL-MODEL-NOT-ALLOWED." in output
    assert "with gemini-2.5-pro it was denied by POL-MODEL-NOT-ALLOWED." in output
    assert "The internal rule IR-CREDENTIAL-IN-PROMPT refused the request" in output
    assert "Before a review the internal rule IR-HIGH-RISK-NOT-REVIEWED denied it" in output
    assert "an approved model. It is classified as a prohibited practice" in output
    assert "client-retail has a hard budget" in output
    assert "The coding IDE is shown only read_file" in output
    assert "deleting a branch was denied by MCP-CALL-NOT-GRANTED." in output
    assert "nordwind / lab" in output
    assert "no broken link" in output
    assert f"Wrote {page}" in output
    assert "It does not provide legal advice." in output
    assert "DIVERSO" not in again
    assert again.count("[come previsto dallo scenario]") == 13
    assert "era già stata rivista" in again
    # The page of the run: one file, nothing loaded from elsewhere, figures of the run.
    assert first.startswith("<!DOCTYPE html>")
    assert '<html lang="en">' in first
    assert "13 of 13 steps went as expected" in first
    # It tells the day as a story: who, when, what they did and what Arbiter did.
    for told in ("A day at Nordwind", "Giulia Conti", "09:40", "Marco Rinaldi", "Stopped"):
        assert told in first
    assert "http://" not in first
    assert "https://" not in first
    for expected in ("Coding IDE", "Code assistant", "gpt-4o", "gemini-2.5-pro", "not approved"):
        assert expected in first
    assert "No declared tool" in first
    assert "1 refused" in first
    assert "3 went through" in first
    assert '<html lang="it">' in second
    assert "13 passi su 13 sono andati come previsto" in second
    assert "Una giornata alla Nordwind" in second
    assert "Fermata" in second
    assert "Nessuno strumento dichiarato" in second
    # No request text reaches the page: it holds what the gateway recorded, and no more.
    assert "anna.bianchi" not in first
    assert "IT60X" not in first
    # The firm has a tenant of its own: nothing of it is in the others.
    assert "No AI system is declared." in arbiter("systems", "list")
    assert "coding-ide" in arbiter("systems", "list", "--tenant", "demo-consulting")
    assert "Error: " in arbiter("demo", "tour", "--case", "nope", ok=False)
    assert "Error: --report is for the consulting case" in arbiter(
        "demo", "tour", "--report", str(page), ok=False
    )
