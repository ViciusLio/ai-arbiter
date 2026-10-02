"""The CLI runs its own event loop, so these tests are synchronous."""

import sqlite3
import sys
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from ai_arbiter import __version__
from ai_arbiter.cli.main import DISCLAIMER, app
from ai_arbiter.cli.serve import parse_roles
from ai_arbiter.core.config import Role, Settings

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"arbiter {__version__}"


def test_no_arguments_shows_help_with_the_disclaimer() -> None:
    result = runner.invoke(app, [])

    assert "Usage" in result.output
    assert "does not provide legal advice" in result.output


def test_init_creates_configuration_database_and_local_tenant(tmp_path: Path) -> None:
    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "arbiter.yaml").is_file()
    assert DISCLAIMER in result.output
    database_file = tmp_path / ".arbiter" / "arbiter.db"
    assert database_file.is_file()
    connection = sqlite3.connect(database_file)
    try:
        assert connection.execute("SELECT slug FROM tenant").fetchall() == [("local",)]
    finally:
        connection.close()


def test_init_twice_keeps_the_configuration_and_the_data(tmp_path: Path) -> None:
    runner.invoke(app, ["init"])
    config = tmp_path / "arbiter.yaml"
    config.write_text(config.read_text(encoding="utf-8") + "\n# edited by hand\n", encoding="utf-8")

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0, result.output
    assert "Keeping existing configuration" in result.output
    assert "# edited by hand" in config.read_text(encoding="utf-8")


def test_init_force_rewrites_the_configuration(tmp_path: Path) -> None:
    config = tmp_path / "arbiter.yaml"
    config.write_text("environment: old\n", encoding="utf-8")

    result = runner.invoke(app, ["init", "--force"])

    assert result.exit_code == 0, result.output
    assert "environment: local" in config.read_text(encoding="utf-8")


def test_init_reports_an_invalid_existing_configuration(tmp_path: Path) -> None:
    (tmp_path / "arbiter.yaml").write_text("unknown_key: 1\n", encoding="utf-8")

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    assert "Error: invalid configuration: unknown_key" in result.output


def test_db_current_distinguishes_migrated_from_unmigrated() -> None:
    before = runner.invoke(app, ["db", "current"])
    upgrade = runner.invoke(app, ["db", "upgrade"])
    after = runner.invoke(app, ["db", "current"])

    assert before.exit_code == 1
    assert "database: not migrated" in before.output
    assert upgrade.exit_code == 0, upgrade.output
    assert "Schema is at revision 0001" in upgrade.output
    assert after.exit_code == 0
    assert "database: 0001" in after.output


def test_config_show_masks_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ARBITER_DATABASE__URL", "postgresql+asyncpg://arbiter:s3cret@db.example/arbiter"
    )

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0, result.output
    assert "s3cret" not in result.output
    assert "arbiter:***@db.example" in result.output


def test_config_file_option_is_honoured(tmp_path: Path) -> None:
    custom = tmp_path / "custom.yaml"
    custom.write_text("environment: from-option\n", encoding="utf-8")

    result = runner.invoke(app, ["--config", str(custom), "config", "show"])

    assert result.exit_code == 0, result.output
    assert "environment: from-option" in result.output


def test_missing_config_file_is_an_error_not_a_traceback(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--config", str(tmp_path / "nope.yaml"), "config", "show"])

    assert result.exit_code == 1
    assert "Error: configuration file not found" in result.output


def test_plugins_list_marks_active_plugins() -> None:
    result = runner.invoke(app, ["plugins", "list"])

    assert result.exit_code == 0, result.output
    lines = [line.split() for line in result.output.splitlines()]
    assert ["env", "active"] in lines
    assert ["in_process", "active"] in lines


def test_plugins_list_flags_a_configured_plugin_that_is_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARBITER_PLUGINS__SECRET_STORE", "vault")

    result = runner.invoke(app, ["plugins", "list"])

    assert "vault" in result.output
    assert "configured but NOT installed" in result.output
    assert ["env", "installed"] in [line.split() for line in result.output.splitlines()]


def test_serve_without_the_gateway_extra_explains_what_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "uvicorn", None)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 1
    assert 'pip install "ai-arbiter[gateway]"' in result.output


def test_serve_starts_the_application_with_the_requested_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uvicorn = pytest.importorskip("uvicorn")
    api = pytest.importorskip("ai_arbiter.gateway.api.app")
    started: dict[str, object] = {}
    built: list[Settings] = []

    def fake_create_app(settings: Settings) -> str:
        built.append(settings)
        return "the-application"

    def fake_run(application: object, **kwargs: object) -> None:
        started.update(kwargs, application=application)

    monkeypatch.setattr(api, "create_app", fake_create_app)
    monkeypatch.setattr(uvicorn, "run", fake_run)

    result = runner.invoke(app, ["serve", "--port", "9999", "--roles", "gateway, admin"])

    assert result.exit_code == 0, result.output
    assert started == {
        "application": "the-application",
        "host": "127.0.0.1",
        "port": 9999,
        "log_level": "info",
    }
    assert built[0].server.roles == {Role.GATEWAY, Role.ADMIN}


def test_serve_rejects_unknown_roles() -> None:
    result = runner.invoke(app, ["serve", "--roles", "gateway,janitor"])

    assert result.exit_code != 0
    assert "valid roles are: admin, gateway, worker" in result.output


def test_parse_roles_normalises_and_validates() -> None:
    assert parse_roles(" worker , gateway,gateway ") == ["gateway", "worker"]
    with pytest.raises(typer.BadParameter):
        parse_roles(" , ")


@pytest.mark.parametrize("command", [["db", "upgrade"], ["db", "current"], ["init"]])
def test_postgresql_without_the_driver_is_an_error_not_a_traceback(
    command: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "asyncpg", None)
    monkeypatch.setenv("ARBITER_DATABASE__URL", "postgresql+asyncpg://arbiter@localhost/arbiter")

    result = runner.invoke(app, command)

    assert result.exit_code == 1
    assert "Error: PostgreSQL support needs the 'gateway' extra" in result.output
    assert 'pip install "ai-arbiter[gateway]"' in result.output
