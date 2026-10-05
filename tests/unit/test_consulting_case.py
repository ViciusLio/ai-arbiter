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
