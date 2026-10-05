"""``arbiter budgets`` end to end. Synchronous: the CLI runs its own event loop."""

import re

from tests.integration.test_cli_compliance import arbiter, workspace


def test_a_budget_is_created_listed_and_deleted_from_the_command_line() -> None:
    arbiter("init")

    empty = arbiter("budgets", "list")
    created = arbiter("budgets", "create", "--limit", "50", "--hard")
    listed = arbiter("budgets", "list")
    budget_id = listed.split()[0]
    deleted = arbiter("budgets", "delete", budget_id)

    assert "No budget is set." in empty
    assert re.search(r"tenant\s+\S+\s+month\s+hard\s+0\.000000 of 50\.000000 USD\s+ok", created)
    assert listed.splitlines()[0] == created.strip()
    assert "an estimate from the price catalogue, not an invoice" in listed
    assert deleted.strip().endswith(f"{budget_id}.")
    assert "No budget is set." in arbiter("budgets", "list")
    audit = arbiter("report", "audit")
    assert "| `budget.created` |" in audit
    assert "| `budget.deleted` |" in audit


def test_a_budget_on_a_declared_system_is_named_by_its_key() -> None:
    workspace()

    created = arbiter(
        "budgets", "create", "--system", "cv-screening", "--limit", "10.50", "--period", "day"
    )

    assert re.search(r"ai_system\s+\S+\s+day\s+soft\s+0\.000000 of 10\.500000 USD\s+ok", created)
    assert "Error: no system with key 'nope'" in arbiter(
        "budgets", "create", "--system", "nope", "--limit", "1", ok=False
    )


def test_budgets_that_cannot_be_checked_are_refused() -> None:
    arbiter("init")
    arbiter("budgets", "create", "--limit", "50")

    assert "Error: this scope already has a budget for that period" in arbiter(
        "budgets", "create", "--limit", "60", ok=False
    )
    assert "Error: --limit:" in arbiter("budgets", "create", "--limit", "many", ok=False)
    assert "Error: a budget on a team needs its id" in arbiter(
        "budgets", "create", "--scope", "team", "--limit", "5", "--period", "day", ok=False
    )
    assert "Error: a budget in EUR cannot be checked" in arbiter(
        "budgets", "create", "--limit", "5", "--period", "day", "--currency", "EUR", ok=False
    )
    assert "Error: no budget with the id 'zzz'" in arbiter("budgets", "delete", "zzz", ok=False)
    assert "Error: use either --id or --system KEY" in arbiter(
        "budgets",
        "create",
        "--limit",
        "5",
        "--system",
        "x",
        "--id",
        "00000000-0000-0000-0000-000000000000",
        ok=False,
    )


def test_two_budgets_created_together_have_different_short_ids() -> None:
    arbiter("init")
    arbiter("budgets", "create", "--limit", "50")
    arbiter("budgets", "create", "--limit", "5", "--period", "day")

    first, second = (line.split()[0] for line in arbiter("budgets", "list").splitlines()[:2])
    arbiter("budgets", "delete", first)
    left = arbiter("budgets", "list")

    assert first != second
    assert left.split()[0] == second
