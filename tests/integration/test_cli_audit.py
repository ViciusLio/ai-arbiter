"""``arbiter audit``. The CLI runs its own event loop, so these tests are synchronous."""

import asyncio
import json
import sqlite3
from pathlib import Path

from sqlalchemy import select
from typer.testing import CliRunner

from ai_arbiter.cli.main import app
from ai_arbiter.core.audit import AuditRecord, DatabaseAuditLog
from ai_arbiter.core.config import load_settings
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import Tenant

runner = CliRunner()


async def _append(count: int) -> None:
    database = Database(load_settings().database.url)
    try:
        async with database.transaction() as session:
            tenant_id = await session.scalar(select(Tenant.id).where(Tenant.slug == "local"))
            assert tenant_id is not None
            for number in range(count):
                await DatabaseAuditLog().append(
                    session, tenant_id, AuditRecord(action="test", outcome=str(number))
                )
    finally:
        await database.dispose()


def workspace_with_entries(count: int) -> None:
    assert runner.invoke(app, ["init"]).exit_code == 0
    asyncio.run(_append(count))


def test_verify_reports_a_sound_chain() -> None:
    workspace_with_entries(3)

    result = runner.invoke(app, ["audit", "verify"])

    assert result.exit_code == 0, result.output
    assert "Audit chain verified: 3 entries, no broken link." in result.output
    assert "Head: entry 3, hash " in result.output


def test_verify_on_an_empty_chain() -> None:
    workspace_with_entries(0)

    result = runner.invoke(app, ["audit", "verify"])

    assert result.exit_code == 0, result.output
    assert "0 entries" in result.output


def test_verify_fails_and_names_the_entry_when_the_chain_was_changed(tmp_path: Path) -> None:
    workspace_with_entries(3)
    connection = sqlite3.connect(tmp_path / ".arbiter" / "arbiter.db")
    connection.execute("UPDATE audit_entry SET outcome = 'changed' WHERE seq = 2")
    connection.commit()
    connection.close()

    result = runner.invoke(app, ["audit", "verify"])

    assert result.exit_code == 1
    assert "Audit chain BROKEN at entry 2: entry hash does not match its content." in result.output
    assert "1 entries before it are sound" in result.output


def test_an_export_can_be_verified_from_the_file(tmp_path: Path) -> None:
    workspace_with_entries(3)
    target = tmp_path / "audit.jsonl"

    exported = runner.invoke(app, ["audit", "export", "--output", str(target)])
    verified = runner.invoke(app, ["audit", "verify", "--file", str(target)])

    assert exported.exit_code == 0, exported.output
    assert "Exported 3 entries" in exported.output
    assert len(target.read_text(encoding="utf-8").splitlines()) == 5
    assert verified.exit_code == 0, verified.output
    assert "3 entries, no broken link" in verified.output


def test_an_edited_export_file_does_not_verify(tmp_path: Path) -> None:
    workspace_with_entries(2)
    target = tmp_path / "audit.jsonl"
    runner.invoke(app, ["audit", "export", "-o", str(target)])
    target.write_text(
        target.read_text(encoding="utf-8").replace('"outcome":"0"', '"outcome":"9"'),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["audit", "verify", "--file", str(target)])

    assert result.exit_code == 1
    assert "BROKEN at entry 1" in result.output


def test_export_goes_to_standard_output_by_default() -> None:
    workspace_with_entries(1)

    result = runner.invoke(app, ["audit", "export"])

    lines = [json.loads(line) for line in result.output.splitlines()]
    assert [line["type"] for line in lines] == ["header", "entry", "head"]


def test_verifying_a_file_that_does_not_exist_is_an_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit", "verify", "--file", str(tmp_path / "absent.jsonl")])

    assert result.exit_code == 1
    assert "Error: file not found" in result.output


def test_an_unknown_tenant_is_an_error_not_a_traceback() -> None:
    workspace_with_entries(0)

    result = runner.invoke(app, ["audit", "verify", "--tenant", "nope"])

    assert result.exit_code == 1
    assert "Error: tenant 'nope' not found" in result.output


def test_a_workspace_that_was_never_initialised_is_an_error_not_a_traceback() -> None:
    result = runner.invoke(app, ["audit", "verify"])

    assert result.exit_code == 1
    assert "Error: the database is not initialised" in result.output
