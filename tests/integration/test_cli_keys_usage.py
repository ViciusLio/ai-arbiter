"""``arbiter keys`` and ``arbiter usage``. Synchronous: the CLI runs its own event loop."""

import asyncio
import re
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from ai_arbiter.cli.main import app
from ai_arbiter.core.config import load_settings
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.gateway.runtime import build_runtime
from tests.support import chat_request

runner = CliRunner()
KEY = re.compile(r"^arb_[a-z0-9]{12}_[0-9A-Za-z]{49}$", re.MULTILINE)


def init() -> None:
    assert runner.invoke(app, ["init"]).exit_code == 0


def created_key(*arguments: str) -> str:
    result = runner.invoke(app, ["keys", "create", "--name", "ci", *arguments])
    assert result.exit_code == 0, result.output
    match = KEY.search(result.output)
    assert match, result.output
    return match.group()


async def _send(key: str, count: int) -> None:
    """Authenticate with the key and send requests through the chat service."""
    database = Database(load_settings().database.url)
    try:
        runtime = await build_runtime(load_settings(), database)
        async with database.session() as session:
            caller = await runtime.identity.authenticate(session, key)
        for _ in range(count):
            await runtime.chat.complete(caller.context, chat_request("x" * 400, model="mock-small"))
        await runtime.aclose()
    finally:
        await database.dispose()


def test_create_prints_the_key_once_and_stores_only_its_hash(tmp_path: Path) -> None:
    init()

    result = runner.invoke(app, ["keys", "create", "--name", "backend", "--role", "admin"])

    assert result.exit_code == 0, result.output
    key = KEY.search(result.output)
    assert key is not None
    assert "Roles:   admin" in result.output
    assert "Project: default/default" in result.output
    assert "cannot be shown again" in result.output
    connection = sqlite3.connect(tmp_path / ".arbiter" / "arbiter.db")
    try:
        stored = connection.execute("SELECT key_id, key_hash, name FROM api_key").fetchall()
        audited = connection.execute("SELECT action, resource_id FROM audit_entry").fetchall()
    finally:
        connection.close()
    assert len(stored) == 1
    assert key.group().startswith(f"arb_{stored[0][0]}_")
    assert key.group() not in str(stored)
    assert audited == [("api_key.issued", stored[0][0])]


def test_a_created_key_authenticates_with_its_default_role() -> None:
    init()
    key = created_key()

    asyncio.run(_send(key, 1))


def test_keys_reuse_the_team_and_project_and_can_name_others(tmp_path: Path) -> None:
    init()
    created_key()
    created_key()
    created_key("--team", "research", "--project", "lab")

    connection = sqlite3.connect(tmp_path / ".arbiter" / "arbiter.db")
    try:
        teams = connection.execute("SELECT name FROM team ORDER BY name").fetchall()
        projects = connection.execute("SELECT name FROM project ORDER BY name").fetchall()
    finally:
        connection.close()
    assert teams == [("default",), ("research",)]
    assert projects == [("default",), ("lab",)]


def test_list_shows_keys_by_public_id_and_revoke_marks_them() -> None:
    init()
    empty = runner.invoke(app, ["keys", "list"])
    key = created_key()
    key_id = key.split("_")[1]

    listed = runner.invoke(app, ["keys", "list"])
    revoked = runner.invoke(app, ["keys", "revoke", f"arb_{key_id}"])
    after = runner.invoke(app, ["keys", "list"])
    again = runner.invoke(app, ["keys", "revoke", "doesnotexist"])

    assert "No API keys" in empty.output
    assert f"arb_{key_id}  active" in listed.output
    assert key not in listed.output
    assert revoked.exit_code == 0, revoked.output
    assert f"Revoked arb_{key_id}" in revoked.output
    assert f"arb_{key_id}  revoked" in after.output
    assert again.exit_code == 1
    assert "Error: API key 'doesnotexist' not found" in again.output


def test_keys_need_an_initialised_workspace() -> None:
    result = runner.invoke(app, ["keys", "create", "--name", "x"])

    assert result.exit_code == 1
    assert "Error: the database is not initialised" in result.output


def test_the_usage_report_shows_traffic_in_both_languages(tmp_path: Path) -> None:
    init()
    asyncio.run(_send(created_key(), 3))

    english = runner.invoke(app, ["usage", "report"])
    italian = runner.invoke(app, ["usage", "report", "--locale", "it", "--scope", "tenant"])
    target = tmp_path / "usage.md"
    written = runner.invoke(app, ["usage", "report", "-o", str(target)])

    assert english.exit_code == 0, english.output
    assert "# Usage report" in english.output
    assert "| default | 3 | 0 | 0 | 300 | 27 | 0.000061 | 0 | 0 |" in english.output
    assert "does not provide legal advice" in english.output
    assert "# Report dei consumi" in italian.output
    assert "| Local workspace | 3 |" in italian.output
    assert written.exit_code == 0
    assert target.read_text(encoding="utf-8").startswith("# Usage report")


def test_an_empty_period_and_bad_options_are_handled() -> None:
    init()

    empty = runner.invoke(app, ["usage", "report", "--from", "2020-01-01", "--to", "2020-01-31"])
    backwards = runner.invoke(
        app, ["usage", "report", "--from", "2026-02-01", "--to", "2026-01-01"]
    )
    locale = runner.invoke(app, ["usage", "report", "--locale", "fr"])
    tenant = runner.invoke(app, ["usage", "report", "--tenant", "nope"])

    assert "No usage was recorded in this period." in empty.output
    assert "Error: --from is after --to" in backwards.output
    assert "Error: unsupported locale 'fr'" in locale.output
    assert "Error: tenant 'nope' not found" in tenant.output
    assert [backwards.exit_code, locale.exit_code, tenant.exit_code] == [1, 1, 1]
