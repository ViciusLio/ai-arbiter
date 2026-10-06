"""The files of the consulting demonstration (ADR-0056)."""

from importlib import resources

from ai_arbiter.cli.demo_consulting import EXPECTED_TIERS
from ai_arbiter.compliance.inventory.declarations import parse_declarations
from ai_arbiter.core.rules import load_packaged_pack, parse_rule_pack

FILES = resources.files("ai_arbiter").joinpath("scenarios", "consulting")


def test_the_firms_regulation_keeps_every_rule_of_the_default_policy_unchanged() -> None:
    default = load_packaged_pack("policy")
    firm = parse_rule_pack(
        FILES.joinpath("policy.yaml").read_text(encoding="utf-8"), origin="consulting"
    )
    kept = {rule.id: rule for rule in firm.rules}

    assert firm.version.startswith(default.version)
    for rule in default.rules:
        assert kept[rule.id].when == rule.when, rule.id
        assert kept[rule.id].then == rule.then, rule.id
    own = sorted(set(kept) - {rule.id for rule in default.rules})
    assert own == ["IR-CREDENTIAL-IN-PROMPT", "IR-HIGH-RISK-NOT-REVIEWED"]
    assert all(kept[rule_id].then.outcome == "deny" for rule_id in own)


def test_the_firm_declares_the_systems_the_demonstration_expects() -> None:
    declared = parse_declarations(
        FILES.joinpath("systems.yaml").read_text(encoding="utf-8"), origin="consulting"
    )

    assert {declaration.key for declaration in declared} == set(EXPECTED_TIERS)


def test_the_page_of_a_run_escapes_what_it_shows_and_loads_nothing() -> None:
    from ai_arbiter.cli.demo_consulting import DemoRun, DemoStep, ToolUse
    from ai_arbiter.cli.demo_report import render_demo_report
    from ai_arbiter.core.i18n import Translator

    run = DemoRun(
        steps=(
            DemoStep("inventory", "A <b>title</b>", True, "Counted"),
            DemoStep(
                "other_engine",
                "Scene <b>title</b>",
                True,
                "</script><script>alert(1)</script>",
                when="09:40",
                who="giulia",
                story="She pastes <img src=x onerror=alert(2)>",
                verdict="blocked",
                rule="POL-MODEL-NOT-ALLOWED",
            ),
            DemoStep("audit", "Second", False, "It differs"),
        ),
        pack_version="1+test",
        systems=(
            {
                "key": "coding-ide",
                "name": "Coding <i>IDE</i>",
                "purpose": "Code",
                "classification": {"tier": "minimal", "status": "confirmed"},
            },
        ),
        usage=(
            ToolUse("Coding IDE", "claude-sonnet-5-5", True, 2, 0),
            ToolUse("Coding IDE", "gpt-4o", False, 0, 3),
        ),
        findings=({"severity": "critical", "text": "A finding & more", "system": "Coding IDE"},),
        candidates=("nordwind / lab",),
        audit_entries=7,
        audit_head="abc123",
    )

    page = render_demo_report(run, Translator("en"))

    assert "2 of 3 steps went as expected" in page
    assert "Coding &lt;i&gt;IDE&lt;/i&gt;" in page
    assert "A finding &amp; more" in page
    assert "<script>alert(1)</script>" not in page
    assert "<img src=x" not in page
    assert "Scene &lt;b&gt;title&lt;/b&gt;" in page
    assert "09:40" in page
    assert "Giulia Conti" in page
    assert "Stopped" in page
    assert "POL-MODEL-NOT-ALLOWED" in page
    assert "2 went through" in page
    assert "3 refused" in page
    assert "Confirmed by a person" in page
    assert "nordwind / lab" in page
    assert "abc123" in page
    assert "http://" not in page
    assert "https://" not in page
