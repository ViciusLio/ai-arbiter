from datetime import date
from pathlib import Path

import pytest

from ai_arbiter.compliance.classifier.engine import classify, ordered_questions
from ai_arbiter.compliance.inventory.declarations import (
    DeclarationError,
    load_declarations,
    parse_declarations,
)
from ai_arbiter.core.domain.risk import ActorRole, RiskTier
from ai_arbiter.core.rules import Facts, RulePack, load_packaged_pack

EXAMPLES = Path(__file__).parents[2] / "examples" / "systems.yaml"
DEPLOYER = frozenset({ActorRole.DEPLOYER})


@pytest.fixture(scope="module")
def pack() -> RulePack:
    return load_packaged_pack("ai-act")


@pytest.fixture(scope="module")
def examples() -> dict[str, Facts]:
    return {system.key: system.answered() for system in load_declarations(EXAMPLES)}


def answered(examples: dict[str, Facts], **overrides: object) -> Facts:
    """A system with every question answered "no", and then the overrides."""
    return {**examples["invoice-data-extraction"], **overrides}  # type: ignore[dict-item]


def ids(result: object) -> list[str]:
    return [obligation.id for obligation in result.obligations]  # type: ignore[attr-defined]


def test_the_pack_states_its_sources_and_that_its_review_is_pending(pack: RulePack) -> None:
    regulation = pack.regulation

    assert regulation is not None
    assert regulation.verified_against == "primary"
    assert regulation.review == "pending"
    assert [source.celex for source in regulation.sources] == [
        "32024R1689",
        "32026R1744",
        "02024R1689-20260727",
    ]
    assert regulation.amended_by == ("Regulation (EU) 2026/1744",)


def test_every_rule_cites_a_provision(pack: RulePack) -> None:
    assert all(rule.then.legal_refs for rule in pack.rules)
    assert all(spec.ref and spec.stage for spec in pack.facts.values())


def test_application_dates_follow_the_amended_article_113(pack: RulePack) -> None:
    dates = {rule.id: rule.then.applies_from for rule in pack.rules}

    assert dates["AIA-ART5-1F-EMOTION-INFERENCE"] == date(2025, 2, 2)
    assert dates["AIA-ART5-1BA-INTIMATE-CONTENT"] == date(2026, 12, 2)
    assert dates["AIA-ART5-1BB-CSAM"] == date(2026, 12, 2)
    assert dates["AIA-ART50-3-EMOTION-BIOMETRIC"] == date(2026, 8, 2)
    assert dates["AIA-ANNEX3-4A-RECRUITMENT"] == date(2027, 12, 2)
    assert dates["AIA-ART6-1-ANNEX1-PRODUCT"] == date(2028, 8, 2)
    annex3 = [rule for rule in pack.rules if rule.id.startswith("AIA-ANNEX3-")]
    assert len(annex3) == 25
    assert {rule.then.applies_from for rule in annex3} == {date(2027, 12, 2)}


def test_a_system_with_nothing_special_is_minimal(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    result = classify(pack, examples["invoice-data-extraction"], DEPLOYER)

    assert result.tier is RiskTier.MINIMAL
    assert result.complete
    assert ids(result) == ["AIA-ART4-AI-LITERACY"]
    assert result.decision.outcome == "tier:minimal"


def test_with_no_answers_the_tier_is_undetermined_and_the_scope_is_asked_first(
    pack: RulePack,
) -> None:
    result = classify(pack, {}, DEPLOYER)

    assert result.tier is RiskTier.UNDETERMINED
    assert not result.complete
    assert ordered_questions(pack, result.missing_facts)[:2] == [
        "scope.is_ai_system",
        "scope.union_nexus",
    ]


def test_a_partly_answered_system_stays_undetermined(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    result = classify(pack, examples["marketing-copy-generator"], DEPLOYER)

    assert result.tier is RiskTier.UNDETERMINED
    assert "prohibited.social_scoring" in result.missing_facts
    assert "annex3.employment" in result.missing_facts
    # Details of an area are not asked before the area itself.
    assert "annex3.employment_recruitment" not in result.missing_facts


@pytest.mark.parametrize(
    ("fact", "value", "rule"),
    [
        ("scope.is_ai_system", False, "AIA-ART3-NOT-AN-AI-SYSTEM"),
        ("scope.union_nexus", False, "AIA-ART2-1-NO-UNION-NEXUS"),
        ("scope.military_defence_national_security", True, "AIA-ART2-3-MILITARY"),
        ("scope.scientific_research_only", True, "AIA-ART2-6-RESEARCH"),
        ("scope.pre_market_development", True, "AIA-ART2-8-PRE-MARKET"),
        ("scope.personal_non_professional", True, "AIA-ART2-10-PERSONAL-USE"),
    ],
)
def test_exclusions_put_a_system_out_of_scope_whatever_else_is_declared(
    pack: RulePack, examples: dict[str, Facts], fact: str, value: bool, rule: str
) -> None:
    facts = answered(examples, **{fact: value, "prohibited.social_scoring": True})

    result = classify(pack, facts, DEPLOYER)

    assert result.tier is RiskTier.OUT_OF_SCOPE
    assert [match.rule_id for match in result.matches] == [rule]
    assert result.obligations == ()
    assert result.complete


def test_an_exclusion_settles_the_result_even_with_other_questions_unanswered(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    result = classify(pack, examples["demand-forecast-prototype"], frozenset({ActorRole.PROVIDER}))

    assert result.tier is RiskTier.OUT_OF_SCOPE
    assert result.roles_not_covered == ("provider",)


@pytest.mark.parametrize(
    "fact",
    [
        "prohibited.manipulative_techniques",
        "prohibited.exploits_vulnerabilities",
        "prohibited.intimate_content_without_consent",
        "prohibited.child_sexual_abuse_material",
        "prohibited.social_scoring",
        "prohibited.crime_prediction_by_profiling",
        "prohibited.facial_image_scraping",
        "prohibited.biometric_categorisation_sensitive",
    ],
)
def test_each_prohibited_practice_gives_the_prohibited_tier(
    pack: RulePack, examples: dict[str, Facts], fact: str
) -> None:
    result = classify(pack, answered(examples, **{fact: True}), DEPLOYER)

    assert result.tier is RiskTier.PROHIBITED
    assert result.matches[1].legal_refs[0].article.startswith("5(1)")


def test_emotion_inference_at_work_is_prohibited_unless_for_medical_or_safety_reasons(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    at_work = answered(examples, **{"prohibited.emotion_inference_work_education": True})

    undecided = classify(pack, at_work, DEPLOYER)
    prohibited = classify(pack, examples["call-centre-mood-monitor"], DEPLOYER)
    excepted = classify(
        pack, {**at_work, "prohibited.emotion_inference_medical_or_safety": True}, DEPLOYER
    )

    assert undecided.tier is RiskTier.UNDETERMINED
    assert undecided.missing_facts == ("prohibited.emotion_inference_medical_or_safety",)
    assert prohibited.tier is RiskTier.PROHIBITED
    assert excepted.tier is RiskTier.MINIMAL


def test_realtime_biometric_identification_is_prohibited_outside_the_listed_objectives(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    base = answered(examples, **{"prohibited.realtime_remote_biometric_identification": True})

    assert (
        classify(
            pack, {**base, "prohibited.realtime_rbi_authorised_objective": False}, DEPLOYER
        ).tier
        is RiskTier.PROHIBITED
    )
    assert (
        classify(
            pack, {**base, "prohibited.realtime_rbi_authorised_objective": True}, DEPLOYER
        ).tier
        is RiskTier.MINIMAL
    )


def test_recruitment_is_high_risk_with_the_obligations_of_a_deployer(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    result = classify(pack, examples["cv-screening"], DEPLOYER)

    assert result.tier is RiskTier.HIGH_RISK
    assert result.complete
    assert ids(result) == [
        "AIA-ART4-AI-LITERACY",
        "AIA-ANNEX3-4A-RECRUITMENT",
        "AIA-ART26-1-INSTRUCTIONS-FOR-USE",
        "AIA-ART26-2-HUMAN-OVERSIGHT",
        "AIA-ART26-4-INPUT-DATA",
        "AIA-ART26-5-MONITORING",
        "AIA-ART26-6-LOGS",
        "AIA-ART26-7-INFORM-WORKERS",
        "AIA-ART26-9-DPIA",
    ]
    by_id = {obligation.id: obligation for obligation in result.obligations}
    assert by_id["AIA-ANNEX3-4A-RECRUITMENT"].legal_refs == ("6(2)", "Annex III(4)(a)")
    assert by_id["AIA-ART26-6-LOGS"].applies_from == date(2027, 12, 2)
    assert by_id["AIA-ART26-6-LOGS"].roles == ("deployer",)


def test_obligations_that_depend_on_who_the_deployer_is(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    public = {
        **examples["cv-screening"],
        "deployer.public_authority": True,
        "deployer.public_law_body_or_public_service": True,
        "deployer.employer_uses_at_workplace": False,
    }
    unanswered = {
        key: value
        for key, value in examples["cv-screening"].items()
        if not key.startswith("deployer.")
    }

    result = classify(pack, public, DEPLOYER)
    open_result = classify(pack, unanswered, DEPLOYER)

    assert "AIA-ART26-8-REGISTRATION" in ids(result)
    assert "AIA-ART27-FUNDAMENTAL-RIGHTS-ASSESSMENT" in ids(result)
    assert "AIA-ART26-7-INFORM-WORKERS" not in ids(result)
    assert open_result.tier is RiskTier.HIGH_RISK
    assert set(open_result.missing_facts) == {
        "deployer.employer_uses_at_workplace",
        "deployer.public_authority",
        "deployer.public_law_body_or_public_service",
    }


def test_credit_scoring_needs_a_fundamental_rights_assessment_whoever_deploys_it(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    facts = {
        **examples["loan-pre-screening"],
        "high_risk.derogation_claimed": False,
        "deployer.public_authority": False,
        "deployer.public_law_body_or_public_service": False,
        "deployer.employer_uses_at_workplace": False,
    }

    result = classify(pack, facts, DEPLOYER)

    assert result.tier is RiskTier.HIGH_RISK
    assert "AIA-ART27-FUNDAMENTAL-RIGHTS-ASSESSMENT" in ids(result)


def test_a_claimed_derogation_takes_an_annex_iii_system_out_of_high_risk(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    result = classify(pack, examples["loan-pre-screening"], DEPLOYER)

    assert result.tier is RiskTier.MINIMAL
    assert "AIA-ART6-3-DEROGATION" in ids(result)
    assert "AIA-ANNEX3-5B-CREDITWORTHINESS" not in ids(result)


def test_profiling_keeps_a_system_high_risk_whatever_derogation_is_claimed(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    facts = {**examples["loan-pre-screening"], "high_risk.profiling_natural_persons": True}

    result = classify(pack, facts, DEPLOYER)

    assert result.tier is RiskTier.HIGH_RISK
    assert "AIA-ART6-3-DEROGATION" not in ids(result)


def test_a_claimed_derogation_asks_whether_the_system_profiles_persons(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    facts = {
        key: value
        for key, value in examples["loan-pre-screening"].items()
        if key != "high_risk.profiling_natural_persons"
    }

    result = classify(pack, facts, DEPLOYER)

    assert result.tier is RiskTier.UNDETERMINED
    assert result.missing_facts[0] == "high_risk.profiling_natural_persons"


def test_a_product_under_annex_i_is_high_risk_only_with_third_party_assessment(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    component = answered(examples, **{"high_risk.annex1_safety_component": True})

    assert classify(pack, component, DEPLOYER).missing_facts == (
        "high_risk.annex1_third_party_assessment",
    )
    assert (
        classify(
            pack, {**component, "high_risk.annex1_third_party_assessment": True}, DEPLOYER
        ).tier
        is RiskTier.HIGH_RISK
    )
    assert (
        classify(
            pack, {**component, "high_risk.annex1_third_party_assessment": False}, DEPLOYER
        ).tier
        is RiskTier.MINIMAL
    )


def test_transparency_obligations_say_which_role_they_are_addressed_to(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    result = classify(pack, examples["customer-support-assistant"], DEPLOYER)

    assert result.tier is RiskTier.TRANSPARENCY
    by_id = {obligation.id: obligation for obligation in result.obligations}
    assert by_id["AIA-ART50-1-INTERACTION"].roles == ("provider",)
    assert by_id["AIA-ART50-1-INTERACTION"].applies_to_declared_roles is False
    assert by_id["AIA-ART4-AI-LITERACY"].applies_to_declared_roles is True
    both = classify(pack, examples["customer-support-assistant"], DEPLOYER | {ActorRole.PROVIDER})
    assert both.obligations[1].applies_to_declared_roles is True
    assert both.roles_not_covered == ("provider",)


def test_published_text_under_editorial_control_needs_no_disclosure(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    text = answered(examples, **{"transparency.public_interest_text": True})

    assert classify(pack, {**text, "transparency.editorial_control": False}, DEPLOYER).tier is (
        RiskTier.TRANSPARENCY
    )
    assert classify(pack, {**text, "transparency.editorial_control": True}, DEPLOYER).tier is (
        RiskTier.MINIMAL
    )


def test_the_most_severe_outcome_wins_and_the_others_stay_in_the_result(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    facts = {
        **examples["cv-screening"],
        "transparency.deep_fake": True,
        "prohibited.social_scoring": True,
    }

    result = classify(pack, facts, DEPLOYER)

    assert result.tier is RiskTier.PROHIBITED
    assert {
        "AIA-ART5-1C-SOCIAL-SCORING",
        "AIA-ANNEX3-4A-RECRUITMENT",
        "AIA-ART50-4-DEEP-FAKE",
    } <= set(ids(result))


def test_the_same_facts_always_give_the_same_digest_and_a_change_gives_another(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    facts = examples["cv-screening"]

    first = classify(pack, facts, DEPLOYER).decision.input_digest
    again = classify(pack, dict(reversed(list(facts.items()))), DEPLOYER).decision.input_digest
    changed = classify(pack, {**facts, "annex3.education": True}, DEPLOYER).decision.input_digest
    other_role = classify(pack, facts, frozenset({ActorRole.PROVIDER})).decision.input_digest
    ignored = classify(pack, {**facts, "controls.anything": True}, DEPLOYER).decision.input_digest

    assert first == again == ignored
    assert len({first, changed, other_role}) == 3


def test_the_decision_names_the_pack_and_says_its_review_is_pending(
    pack: RulePack, examples: dict[str, Facts]
) -> None:
    decision = classify(pack, examples["cv-screening"], DEPLOYER).decision

    assert decision.details["pack"] == "ai-act"
    assert decision.details["pack_version"] == pack.version
    assert decision.details["pack_review"] == "pending"
    assert decision.audit_payload()["kind"] == "classification"


def test_the_example_file_declares_seven_invented_systems() -> None:
    systems = load_declarations(EXAMPLES)

    assert len(systems) == 7
    assert all(system.roles for system in systems)
    assert systems[0].use == []
    assert systems[0].facts["scope.is_ai_system"] is True


def test_declarations_are_validated() -> None:
    cases = [
        ("systems: []", "systems"),
        ("systems: [{ key: Bad Key, name: x }]", "key"),
        ("systems: [{ key: a, name: x }, { key: a, name: y }]", "used twice"),
        ("systems: [{ key: a, name: x, use: [nope] }]", "unknown fact set 'nope'"),
        ("systems: [{ key: a, name: x, roles: [{ role: owner }] }]", "role"),
        ("systems: [{ key: a, name: x, facts: { f: 1.5 } }]", "facts"),
        ("systems: [{ key: a, name: x, surprise: 1 }]", "surprise"),
        ("systems: [", "not valid YAML"),
    ]
    for text, message in cases:
        with pytest.raises(DeclarationError, match=message):
            parse_declarations(text)
    with pytest.raises(DeclarationError, match="not found"):
        load_declarations(Path("absent.yaml"))


def test_an_answer_left_empty_is_not_an_answer() -> None:
    system = parse_declarations(
        "fact_sets: { base: { a.b: true, c.d: false } }\n"
        "systems: [{ key: s, name: S, use: [base], facts: { c.d: null, e.f: true } }]"
    )[0]

    assert system.answered() == {"a.b": True, "e.f": True}
