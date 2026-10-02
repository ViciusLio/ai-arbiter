"""``arbiter report`` end to end. Synchronous: the CLI runs its own event loop."""

from pathlib import Path

from tests.integration.test_cli_compliance import arbiter, workspace


def test_a_system_report_is_printed_or_written_in_each_language_and_format(
    tmp_path: Path,
) -> None:
    workspace()
    arbiter("systems", "review", "cv-screening", "--confirm", "--reviewer", "Ada Lovelace")
    arbiter("scan")

    printed = arbiter("report", "system", "cv-screening", "--locale", "it")
    written = arbiter(
        "report", "system", "cv-screening", "--locale", "all", "--format", "both",
        "-o", str(tmp_path / "out"),
    )  # fmt: skip
    files = sorted(path.name for path in (tmp_path / "out").iterdir())

    assert printed.startswith("# Report di sistema: CV screening\n")
    assert "- **Classe**: Alto rischio" in printed
    assert "Ada Lovelace" not in printed
    assert written.count("Wrote ") == 4
    assert all(name.startswith("report-system-cv-screening-") for name in files)
    assert [name.split(".", 1)[1] for name in files] == ["en.html", "en.md", "it.html", "it.md"]
    html = next((tmp_path / "out").glob("*.en.html")).read_text(encoding="utf-8")
    assert "<h1>System report: CV screening</h1>" in html


def test_a_system_report_refuses_what_it_cannot_do() -> None:
    workspace()

    assert "Error: " in arbiter("report", "system", "no-such-system", ok=False)
    assert "Error: unsupported locale 'fr'" in arbiter(
        "report", "system", "cv-screening", "--locale", "fr", ok=False
    )
    assert "Error: several outputs need a directory" in arbiter(
        "report", "system", "cv-screening", "--format", "both", ok=False
    )


def test_an_audit_report_covers_the_period_asked_for(tmp_path: Path) -> None:
    workspace()

    recent = arbiter("report", "audit")
    old = arbiter("report", "audit", "--since", "2020-01-01", "--until", "2020-01-31")
    written = arbiter("report", "audit", "--format", "html", "-o", str(tmp_path))
    html = next(tmp_path.glob("report-audit-*.en.html")).read_text(encoding="utf-8")

    assert recent.startswith("# Audit report\n")
    assert "no broken link" in recent
    assert "| `system.declared` |" in recent
    assert "No audit entry in this period." in old
    assert "no broken link" in old
    assert written.count("Wrote ") == 1
    assert "<h1>Audit report</h1>" in html
    assert "Error: the period is empty" in arbiter(
        "report", "audit", "--since", "2026-02-01", "--until", "2026-01-01", ok=False
    )
