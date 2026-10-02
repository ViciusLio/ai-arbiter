"""``arbiter pii``. The CLI runs its own event loop, so these tests are synchronous."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_arbiter.cli.main import app

runner = CliRunner()


def test_detectors_lists_what_is_validated_and_what_is_missed() -> None:
    result = runner.invoke(app, ["pii", "detectors"])

    assert result.exit_code == 0, result.output
    assert "Active detector: builtin" in result.output
    for category in ("email", "iban", "it_fiscal_code", "secret"):
        assert f"\n{category}\n" in result.output
    assert result.output.count("validates:") == result.output.count("misses:") == 8
    assert "do not detect names" in result.output
    assert "does not provide legal advice" in result.output


def test_redact_masks_a_file(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text(
        "Scrivi a mario@example.com\nIBAN IT60X0542811101000000123456\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["pii", "redact", str(source)])

    assert result.exit_code == 0, result.output
    assert "Scrivi a [EMAIL]\nIBAN [IBAN]\n" in result.output
    assert "mario@example.com" not in result.output
    assert "Detected: email, iban (2 occurrences)" in result.output


def test_redact_reads_standard_input() -> None:
    result = runner.invoke(app, ["pii", "redact"], input="call +39 347 1234567")

    assert result.exit_code == 0, result.output
    assert "call [PHONE]" in result.output


def test_redact_says_when_nothing_was_found() -> None:
    result = runner.invoke(app, ["pii", "redact"], input="plain text")

    assert "plain text" in result.output
    assert "Detected: nothing (0 occurrences)" in result.output


def test_redact_of_a_missing_file_is_an_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["pii", "redact", str(tmp_path / "absent.txt")])

    assert result.exit_code == 1
    assert "Error: file not found" in result.output


def test_an_unknown_detector_plugin_is_an_error_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARBITER_PLUGINS__PII_DETECTOR", "nope")

    result = runner.invoke(app, ["pii", "detectors"])

    assert result.exit_code == 1
    assert "Error: unknown plugin 'nope' for 'pii_detectors'" in result.output
