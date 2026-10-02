from datetime import date
from pathlib import Path

import pytest

from ai_arbiter.core.rules import (
    Decision,
    DecisionKind,
    Facts,
    RuleEvaluationError,
    RuleKind,
    RulePack,
    RulePackError,
    condition_state,
    evaluate,
    evaluate_partial,
    facts_digest,
    load_packaged_pack,
    load_rule_pack,
    packaged_versions,
    parse_rule_pack,
)

PACK = """
pack: demo
version: "1.0.0"
regulation:
  id: "Regulation (EU) 2024/1689"
  as_of: 2026-10-02
  verified_against: secondary
facts:
  capabilities.emotion_recognition: boolean
  context.setting: string
  purpose.medical_or_safety: boolean
  request.tokens: integer
  pii.categories: list
rules:
  - id: AIA-ART5-1F
    kind: classification
    roles: [provider, deployer]
    when:
      all:
        - { fact: capabilities.emotion_recognition, eq: true }
        - { fact: context.setting, in: [workplace, education] }
        - not: { fact: purpose.medical_or_safety, eq: true }
    then:
      outcome: prohibited
      legal_refs: [{ article: "5(1)(f)" }]
      applies_from: 2025-02-02
      message_key: aia.art5.1f
  - id: POL-LARGE
    kind: policy
    when:
      any:
        - { fact: request.tokens, gt: 1000 }
        - { fact: pii.categories, contains: iban }
    then: { outcome: deny, message_key: policy.large }
  - id: POL-SMALL
    kind: policy
    when: { fact: request.tokens, lt: 10 }
    then: { outcome: allow, message_key: policy.small }
"""


@pytest.fixture
def pack() -> RulePack:
    return parse_rule_pack(PACK)


def test_a_rule_matches_when_all_its_conditions_hold(pack: RulePack) -> None:
    matches = evaluate(
        pack,
        RuleKind.CLASSIFICATION,
        {
            "capabilities.emotion_recognition": True,
            "context.setting": "workplace",
            "purpose.medical_or_safety": False,
        },
    )

    assert [match.rule_id for match in matches] == ["AIA-ART5-1F"]
    match = matches[0]
    assert (match.pack, match.pack_version, match.outcome) == ("demo", "1.0.0", "prohibited")
    assert match.applies_from == date(2025, 2, 2)
    assert [ref.article for ref in match.legal_refs] == ["5(1)(f)"]
    assert [(t.fact, t.operator, t.expected, t.negated) for t in match.matched] == [
        ("capabilities.emotion_recognition", "eq", True, False),
        ("context.setting", "in", ["workplace", "education"], False),
        ("purpose.medical_or_safety", "eq", True, True),
    ]


def test_a_rule_does_not_match_when_one_condition_fails(pack: RulePack) -> None:
    facts: Facts = {
        "capabilities.emotion_recognition": True,
        "context.setting": "workplace",
        "purpose.medical_or_safety": True,
    }

    assert evaluate(pack, RuleKind.CLASSIFICATION, facts) == []


def test_only_rules_of_the_requested_kind_are_evaluated(pack: RulePack) -> None:
    matches = evaluate(pack, RuleKind.POLICY, {"request.tokens": 5000})

    assert [match.rule_id for match in matches] == ["POL-LARGE"]


def test_any_reports_only_the_branches_that_held(pack: RulePack) -> None:
    matches = evaluate(pack, RuleKind.POLICY, {"request.tokens": 50, "pii.categories": ["iban"]})

    assert [(t.fact, t.operator) for t in matches[0].matched] == [("pii.categories", "contains")]


def test_a_missing_fact_satisfies_no_comparison(pack: RulePack) -> None:
    assert evaluate(pack, RuleKind.POLICY, {}) == []
    assert evaluate(pack, RuleKind.POLICY, {"request.tokens": None}) == []


def test_matches_come_in_pack_order() -> None:
    pack = parse_rule_pack(
        """
pack: order
version: "1"
facts: { a: integer }
rules:
  - id: SECOND-IN-NAME
    kind: policy
    when: { fact: a, gt: 0 }
    then: { outcome: x, message_key: k }
  - id: FIRST-IN-NAME
    kind: policy
    when: { fact: a, lt: 100 }
    then: { outcome: y, message_key: k }
"""
    )

    assert [m.rule_id for m in evaluate(pack, RuleKind.POLICY, {"a": 5})] == [
        "SECOND-IN-NAME",
        "FIRST-IN-NAME",
    ]


def _single(
    condition: str, facts_declared: str = "{ a: string, n: integer, b: boolean, l: list }"
) -> RulePack:
    return parse_rule_pack(
        f"""
pack: single
version: "1"
facts: {facts_declared}
rules:
  - id: R
    kind: policy
    when: {condition}
    then: {{ outcome: hit, message_key: k }}
"""
    )


@pytest.mark.parametrize(
    ("condition", "facts", "expected"),
    [
        ("{ fact: a, eq: x }", {"a": "x"}, True),
        ("{ fact: a, eq: x }", {"a": "y"}, False),
        ("{ fact: a, ne: x }", {"a": "y"}, True),
        ("{ fact: a, ne: x }", {"a": "x"}, False),
        ("{ fact: a, ne: x }", {}, False),
        ("{ fact: a, in: [x, y] }", {"a": "y"}, True),
        ("{ fact: a, in: [x, y] }", {"a": "z"}, False),
        ("{ fact: a, contains: ell }", {"a": "hello"}, True),
        ("{ fact: l, contains: x }", {"l": ["x", "y"]}, True),
        ("{ fact: l, contains: x }", {"l": []}, False),
        ("{ fact: n, gt: 3 }", {"n": 4}, True),
        ("{ fact: n, gt: 3 }", {"n": 3}, False),
        ("{ fact: n, lt: 3 }", {"n": 2}, True),
        ("{ fact: n, lt: 3 }", {"n": 3}, False),
        ("{ fact: b, eq: true }", {"b": True}, True),
        ("{ fact: b, eq: false }", {"b": False}, True),
        ("{ fact: a, exists: true }", {"a": "x"}, True),
        ("{ fact: a, exists: true }", {}, False),
        ("{ fact: a, exists: false }", {}, True),
        ("{ fact: a, exists: false }", {"a": None}, True),
        ("{ not: { fact: a, exists: true } }", {}, True),
        (
            "{ not: { any: [{ fact: n, gt: 1 }, { fact: b, eq: true }] } }",
            {"n": 0, "b": False},
            True,
        ),
        (
            "{ not: { any: [{ fact: n, gt: 1 }, { fact: b, eq: true }] } }",
            {"n": 5, "b": False},
            False,
        ),
    ],
)
def test_operators(condition: str, facts: dict[str, object], expected: bool) -> None:
    matches = evaluate(_single(condition), RuleKind.POLICY, facts)  # type: ignore[arg-type]

    assert bool(matches) is expected


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("- a list", "expected a mapping"),
        ("pack: [unclosed", "not valid YAML"),
        ("pack: p\nversion: '1'\nfacts: {}\nrules: []\nextra: 1", "extra"),
        ("pack: Bad Name\nversion: '1'\nfacts: {}\nrules: []", "pack"),
    ],
)
def test_a_malformed_pack_is_rejected(text: str, message: str) -> None:
    with pytest.raises(RulePackError, match=message):
        parse_rule_pack(text)


@pytest.mark.parametrize(
    ("condition", "message"),
    [
        ("{ fact: missing, eq: x }", "does not declare"),
        ("{ fact: a, eq: x, ne: y }", "exactly one of"),
        ("{ fact: a }", "exactly one of"),
        ("{ fact: a, eq: null }", "has no value"),
        ("{ fact: a, matches: '.*' }", "matches"),
        ("{ fact: a, gt: 3 }", "needs an integer fact"),
        ("{ fact: n, gt: 1.5 }", "gt"),
        ("{ fact: n, eq: three }", "compared with the string"),
        ("{ fact: b, eq: 1 }", "compared with the integer"),
        ("{ fact: b, contains: x }", "needs a list or a string"),
        ("{ fact: l, eq: x }", "compare a list with"),
        ("{ fact: 'Not A Name', eq: x }", "invalid fact name"),
        ("{ all: [] }", "at least 1"),
    ],
)
def test_a_rule_that_cannot_be_evaluated_is_rejected_when_the_pack_is_loaded(
    condition: str, message: str
) -> None:
    with pytest.raises(RulePackError, match=message):
        _single(condition)


_RULE = (
    "{{ id: {id}, kind: policy, when: {{ fact: a, eq: x }}, "
    "then: {{ outcome: o, message_key: k }} }}"
)


def test_duplicate_rule_ids_are_rejected() -> None:
    rule = _RULE.format(id="R")

    with pytest.raises(RulePackError, match="used twice"):
        parse_rule_pack(f"pack: p\nversion: '1'\nfacts: {{ a: string }}\nrules: [{rule}, {rule}]")


def test_a_rule_id_must_be_in_capitals() -> None:
    rule = _RULE.format(id="lower")

    with pytest.raises(RulePackError, match="invalid rule id"):
        parse_rule_pack(f"pack: p\nversion: '1'\nfacts: {{ a: string }}\nrules: [{rule}]")


def test_a_fact_of_the_wrong_type_is_an_error_not_a_silent_mismatch(pack: RulePack) -> None:
    with pytest.raises(RuleEvaluationError, match=r"'request\.tokens' must be a integer"):
        evaluate(pack, RuleKind.POLICY, {"request.tokens": "many"})
    with pytest.raises(RuleEvaluationError, match="must be a boolean"):
        evaluate(pack, RuleKind.POLICY, {"capabilities.emotion_recognition": 1})
    with pytest.raises(RuleEvaluationError, match="must be a list"):
        evaluate(pack, RuleKind.POLICY, {"pii.categories": "iban"})


def test_true_is_not_one(pack: RulePack) -> None:
    single = _single("{ fact: n, eq: 1 }")

    assert evaluate(single, RuleKind.POLICY, {"n": 1})
    with pytest.raises(RuleEvaluationError):
        evaluate(single, RuleKind.POLICY, {"n": True})


def test_facts_the_pack_does_not_declare_are_ignored(pack: RulePack) -> None:
    assert evaluate(pack, RuleKind.POLICY, {"unknown.fact": 3.5}) == []  # type: ignore[dict-item]


def test_load_from_a_file(tmp_path: Path) -> None:
    path = tmp_path / "pack.yaml"
    path.write_text(PACK, encoding="utf-8")

    assert load_rule_pack(path).regulation is not None
    with pytest.raises(RulePackError, match="not found"):
        load_rule_pack(tmp_path / "absent.yaml")


def test_the_shipped_policy_pack_loads() -> None:
    versions = packaged_versions("policy")
    pack = load_packaged_pack("policy")

    assert versions
    assert pack.version == versions[-1]
    assert load_packaged_pack("policy", versions[0]).pack == "policy"
    assert {rule.then.outcome for rule in pack.rules} == {"deny", "redact"}


def test_an_unknown_shipped_pack_or_version_is_an_error() -> None:
    with pytest.raises(RulePackError, match=r"no rule pack named 'nope'"):
        load_packaged_pack("nope")
    with pytest.raises(RulePackError, match=r"has no version '0\.0\.0'"):
        load_packaged_pack("policy", "0.0.0")


def test_the_digest_of_facts_ignores_order_and_changes_with_values() -> None:
    assert facts_digest({"a": 1, "b": ["x"]}) == facts_digest({"b": ("x",), "a": 1})
    assert facts_digest({"a": 1}) != facts_digest({"a": 2})


def test_a_decision_serialises_for_the_audit_log_without_fact_values(pack: RulePack) -> None:
    facts: Facts = {"request.tokens": 5000}
    decision = Decision(
        kind=DecisionKind.POLICY,
        outcome="deny",
        matches=tuple(evaluate(pack, RuleKind.POLICY, facts)),
        input_digest=facts_digest(facts),
        details={"note": "x"},
    )

    payload = decision.audit_payload()

    assert payload["kind"] == "policy"
    assert payload["outcome"] == "deny"
    assert payload["matches"] == [
        {
            "rule_id": "POL-LARGE",
            "pack": "demo",
            "pack_version": "1.0.0",
            "outcome": "deny",
            "message_key": "policy.large",
            "applies_from": None,
            "legal_refs": [],
            "matched": [
                {"fact": "request.tokens", "operator": "gt", "expected": 1000, "negated": False}
            ],
        }
    ]
    assert "5000" not in str(payload)


STAGED = """
pack: staged
version: "1"
stages: [scope, area]
facts:
  scope.in: { type: boolean, stage: scope, ref: "Art. 2" }
  area.jobs: { type: boolean, stage: area, ref: "Annex III(4)" }
  area.jobs_recruitment: { type: boolean, stage: area, ref: "Annex III(4)(a)" }
  area.school: { type: boolean, stage: area }
  derogation: boolean
  profiling: boolean
  count: integer
rules:
  - id: OUT
    kind: classification
    when: { fact: scope.in, eq: false }
    then: { outcome: out_of_scope, message_key: k }
  - id: JOBS
    kind: classification
    roles: [deployer]
    when:
      all:
        - { fact: area.jobs, eq: true }
        - { fact: area.jobs_recruitment, eq: true }
        - not: { all: [{ fact: derogation, eq: true }, { fact: profiling, eq: false }] }
    then: { outcome: high_risk, message_key: k, severity: high, severity_before: low }
  - id: EITHER
    kind: classification
    when: { any: [{ fact: area.school, eq: true }, { fact: count, gt: 3 }] }
    then: { outcome: transparency, message_key: k }
outcome_obligations:
  - id: OBL
    outcome: high_risk
    roles: [deployer]
    when: { fact: profiling, eq: true }
    message_key: k
"""


def staged() -> RulePack:
    return parse_rule_pack(STAGED)


def state(facts: Facts) -> tuple[list[str], dict[str, tuple[str, ...]]]:
    result = evaluate_partial(staged(), RuleKind.CLASSIFICATION, facts)
    return [m.rule_id for m in result.matches], {r.rule_id: r.missing for r in result.open}


def test_with_no_facts_every_rule_is_open_and_only_the_first_questions_are_asked() -> None:
    matches, open_rules = state({})

    assert matches == []
    assert open_rules == {
        "OUT": ("scope.in",),
        "JOBS": ("area.jobs",),
        "EITHER": ("area.school", "count"),
    }


def test_an_area_answered_no_settles_its_details_without_asking_them() -> None:
    _, open_rules = state({"area.jobs": False})

    assert "JOBS" not in open_rules


def test_an_area_answered_yes_asks_for_its_details_one_step_at_a_time() -> None:
    assert state({"area.jobs": True})[1]["JOBS"] == ("area.jobs_recruitment",)
    assert state({"area.jobs": True, "area.jobs_recruitment": True})[1]["JOBS"] == ("derogation",)
    assert state({"area.jobs": True, "area.jobs_recruitment": True, "derogation": True})[1][
        "JOBS"
    ] == ("profiling",)


def test_a_missing_answer_is_never_read_as_no() -> None:
    facts: Facts = {"area.jobs": True, "area.jobs_recruitment": True}

    assert evaluate(staged(), RuleKind.CLASSIFICATION, facts)  # two-valued: absent means no
    assert state(facts)[0] == []  # three-valued: absent means "ask"


def test_a_rule_matches_once_everything_it_needs_is_answered() -> None:
    base: Facts = {"area.jobs": True, "area.jobs_recruitment": True}

    assert state({**base, "derogation": False})[0] == ["JOBS"]
    assert state({**base, "derogation": True, "profiling": True})[0] == ["JOBS"]
    matches, open_rules = state({**base, "derogation": True, "profiling": False})
    assert "JOBS" not in matches
    assert "JOBS" not in open_rules


def test_any_is_settled_by_one_true_branch_and_otherwise_needs_them_all() -> None:
    assert state({"count": 9})[0] == ["EITHER"]
    assert state({"count": 1})[1]["EITHER"] == ("area.school",)
    assert "EITHER" not in state({"count": 1, "area.school": False})[1]


def test_missing_facts_are_listed_once_in_the_order_they_are_needed() -> None:
    result = evaluate_partial(staged(), RuleKind.CLASSIFICATION, {})

    assert result.missing_facts == ("scope.in", "area.jobs", "area.school", "count")


def test_a_match_carries_roles_and_severities_of_its_rule() -> None:
    result = evaluate_partial(
        staged(),
        RuleKind.CLASSIFICATION,
        {"area.jobs": True, "area.jobs_recruitment": True, "derogation": False},
    )

    match = result.matches[0]
    assert (match.roles, match.severity, match.severity_before) == (("deployer",), "high", "low")


def test_fact_specs_carry_stage_and_provision_and_bare_types_still_work() -> None:
    pack = staged()

    assert pack.stages == ("scope", "area")
    assert (pack.facts["scope.in"].stage, pack.facts["scope.in"].ref) == ("scope", "Art. 2")
    assert pack.facts["derogation"].type.value == "boolean"
    assert pack.facts["derogation"].stage is None


def test_outcome_obligations_are_validated_like_rules() -> None:
    pack = staged()

    assert pack.outcome_obligations[0].id == "OBL"
    assert condition_state(pack.outcome_obligations[0].when, {}) == (None, ["profiling"])
    assert condition_state(pack.outcome_obligations[0].when, {"profiling": True}) == (True, [])
    with pytest.raises(RulePackError, match="does not declare"):
        parse_rule_pack(
            STAGED.replace(
                "when: { fact: profiling, eq: true }\n    message_key",
                "when: { fact: nope, eq: true }\n    message_key",
            )
        )
    with pytest.raises(RulePackError, match="used twice"):
        parse_rule_pack(STAGED.replace("id: OBL", "id: JOBS"))


def test_a_fact_in_an_unknown_stage_is_rejected() -> None:
    with pytest.raises(RulePackError, match="unknown stage 'nowhere'"):
        parse_rule_pack(STAGED.replace("stage: scope, ref", "stage: nowhere, ref"))


def test_a_regulation_records_its_sources_and_whether_the_owner_reviewed_it() -> None:
    pack = parse_rule_pack(
        STAGED
        + """
regulation:
  id: "Regulation (EU) 2024/1689"
  as_of: 2026-10-02
  verified_against: primary
  sources:
    - celex: 32024R1689
      title: AI Act
      retrieved: 2026-10-02
      url: https://publications.europa.eu/resource/celex/32024R1689
      sha256: 8f0b656302f9864cc87e040c371f209a9d65ae1a6cecc25ca5eb737e872d721a
"""
    )

    assert pack.regulation is not None
    assert pack.regulation.review == "pending"
    assert pack.regulation.sources[0].celex == "32024R1689"
