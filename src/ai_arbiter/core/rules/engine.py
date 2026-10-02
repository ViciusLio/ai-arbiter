"""Rule evaluation with a trace of the conditions that produced each match."""

from collections.abc import Mapping, Sequence
from datetime import date
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.rules.schema import (
    AllOf,
    Comparison,
    FactType,
    LegalRef,
    Not,
    Rule,
    RuleKind,
    RulePack,
)

type FactValue = bool | int | str | Sequence[str] | None
type Facts = Mapping[str, FactValue]

PACK_FILE = "pack.yaml"
_PACKAGED = "ai_arbiter.rulepacks"


class RulePackError(ArbiterError):
    """A rule pack is missing or not valid."""


class RuleEvaluationError(ArbiterError):
    """The facts given to the engine do not match what the pack declares."""


class ConditionTrace(BaseModel):
    """A comparison that contributed to a match.

    It names the fact, the operator and the value written in the rule. The value the
    fact had is not recorded: traces end up in the audit log, which holds no content.
    """

    model_config = ConfigDict(frozen=True)

    fact: str
    operator: str
    expected: Any
    negated: bool = False


class RuleMatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: str
    pack: str
    pack_version: str
    outcome: str
    matched: tuple[ConditionTrace, ...]
    legal_refs: tuple[LegalRef, ...] = ()
    applies_from: date | None = None
    message_key: str
    roles: tuple[str, ...] = ()
    severity: str | None = None
    severity_before: str | None = None


class OpenRule(BaseModel):
    """A rule that cannot be told yet, and the facts to ask for next."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    outcome: str
    missing: tuple[str, ...]


class Evaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    matches: tuple[RuleMatch, ...]
    open: tuple[OpenRule, ...]

    @property
    def missing_facts(self) -> tuple[str, ...]:
        """Facts to ask for next, each once, in the order the rules need them."""
        seen: dict[str, None] = {}
        for rule in self.open:
            for name in rule.missing:
                seen.setdefault(name)
        return tuple(seen)


def _same_type(left: object, right: object) -> bool:
    # ``True == 1`` in Python; a rule that says 1 must not match a fact that is ``True``.
    return isinstance(left, bool) == isinstance(right, bool)


def _holds(comparison: Comparison, facts: Facts) -> bool:
    """Whether a comparison holds. A missing or null fact satisfies only ``exists: false``."""
    value = facts.get(comparison.fact)
    operator, expected = comparison.operator, comparison.expected
    if operator == "exists":
        return (value is not None) is bool(expected)
    if value is None:
        return False
    if operator == "eq":
        return _same_type(value, expected) and value == expected
    if operator == "ne":
        return not (_same_type(value, expected) and value == expected)
    if operator == "in":
        return any(_same_type(value, item) and value == item for item in expected)
    if operator == "contains":
        return expected in value if isinstance(value, str | Sequence) else False
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return bool(value > expected if operator == "gt" else value < expected)


def _trace(comparison: Comparison, *, negated: bool = False) -> ConditionTrace:
    expected = comparison.expected
    return ConditionTrace(
        fact=comparison.fact,
        operator=comparison.operator,
        expected=list(expected) if isinstance(expected, tuple) else expected,
        negated=negated,
    )


def _negate(traces: list[ConditionTrace]) -> list[ConditionTrace]:
    return [trace.model_copy(update={"negated": not trace.negated}) for trace in traces]


def _evaluate(condition: Any, facts: Facts) -> tuple[bool, list[ConditionTrace]]:
    """Return whether the condition holds and the comparisons that explain the result.

    For a condition that holds, those are the comparisons that held; for one that does
    not, the comparisons that failed. ``not`` swaps the two, which is how a rule that
    matches because something is absent still gets a trace.
    """
    if isinstance(condition, Comparison):
        return _holds(condition, facts), [_trace(condition)]
    if isinstance(condition, Not):
        held, traces = _evaluate(condition.not_, facts)
        return not held, _negate(traces)
    results = [
        _evaluate(child, facts)
        for child in (condition.all if isinstance(condition, AllOf) else condition.any)
    ]
    held = (
        all(result for result, _ in results)
        if isinstance(condition, AllOf)
        else any(result for result, _ in results)
    )
    return held, [trace for result, traces in results if result == held for trace in traces]


def _evaluate3(condition: Any, facts: Facts) -> tuple[bool | None, list[ConditionTrace], list[str]]:
    """Three-valued evaluation (ADR-0035): holds, does not hold, or cannot be told.

    Returns the value, the comparisons that explain it and, when it cannot be told, the
    facts to ask for next. ``all`` asks for the facts of its first undecided condition
    only: that is what makes a questionnaire staged, an area being asked before its
    details. ``any`` needs every undecided branch.
    """
    if isinstance(condition, Comparison):
        if condition.operator != "exists" and facts.get(condition.fact) is None:
            return None, [], [condition.fact]
        return _holds(condition, facts), [_trace(condition)], []
    if isinstance(condition, Not):
        value, traces, missing = _evaluate3(condition.not_, facts)
        return (None if value is None else not value), _negate(traces), missing
    conjunction = isinstance(condition, AllOf)
    results = [
        _evaluate3(child, facts) for child in (condition.all if conjunction else condition.any)
    ]
    decisive = not conjunction  # ``any`` is settled by a true branch, ``all`` by a false one
    if any(value is decisive for value, _, _ in results):
        traces = [t for value, child, _ in results if value is decisive for t in child]
        return decisive, traces, []
    undecided = [missing for value, _, missing in results if value is None]
    if undecided:
        asked = undecided[0] if conjunction else [name for item in undecided for name in item]
        return None, [], list(dict.fromkeys(asked))
    return (not decisive), [t for _, child, _ in results for t in child], []


def _check_facts(pack: RulePack, facts: Facts) -> None:
    for name, value in facts.items():
        spec = pack.facts.get(name)
        if spec is None or value is None:
            continue
        declared = spec.type
        valid = {
            FactType.BOOLEAN: isinstance(value, bool),
            FactType.INTEGER: isinstance(value, int) and not isinstance(value, bool),
            FactType.STRING: isinstance(value, str),
            FactType.LIST: not isinstance(value, str)
            and isinstance(value, Sequence)
            and all(isinstance(item, str) for item in value),
        }[declared]
        if not valid:
            raise RuleEvaluationError(
                f"fact '{name}' must be a {declared.value}, got {type(value).__name__}"
            )


def evaluate(pack: RulePack, kind: RuleKind, facts: Facts) -> list[RuleMatch]:
    """Return the rules of ``kind`` that match, in pack order.

    Facts the pack does not declare are ignored. A declared fact with a value of the
    wrong type raises ``RuleEvaluationError``: facts are produced by code, so that is a
    defect, not a rule that fails to match.
    """
    _check_facts(pack, facts)
    matches: list[RuleMatch] = []
    for rule in pack.rules:
        if rule.kind is not kind:
            continue
        held, traces = _evaluate(rule.when, facts)
        if held:
            matches.append(_match(pack, rule, traces))
    return matches


def _match(pack: RulePack, rule: Rule, traces: list[ConditionTrace]) -> RuleMatch:
    return RuleMatch(
        rule_id=rule.id,
        pack=pack.pack,
        pack_version=pack.version,
        outcome=rule.then.outcome,
        matched=tuple(traces),
        legal_refs=rule.then.legal_refs,
        applies_from=rule.then.applies_from,
        message_key=rule.then.message_key,
        roles=rule.roles,
        severity=rule.then.severity,
        severity_before=rule.then.severity_before,
    )


def evaluate_partial(pack: RulePack, kind: RuleKind, facts: Facts) -> Evaluation:
    """Evaluate with missing facts allowed.

    A rule whose condition cannot be told is returned as open, with the facts to ask for
    next, instead of being counted as not matching. A fact that was not answered is
    never read as "no".
    """
    _check_facts(pack, facts)
    matches: list[RuleMatch] = []
    undecided: list[OpenRule] = []
    for rule in pack.rules:
        if rule.kind is not kind:
            continue
        value, traces, missing = _evaluate3(rule.when, facts)
        if value:
            matches.append(_match(pack, rule, traces))
        elif value is None:
            undecided.append(
                OpenRule(rule_id=rule.id, outcome=rule.then.outcome, missing=tuple(missing))
            )
    return Evaluation(matches=tuple(matches), open=tuple(undecided))


def condition_state(condition: Any, facts: Facts) -> tuple[bool | None, list[str]]:
    """Three-valued value of a single condition, and the facts it still needs."""
    value, _, missing = _evaluate3(condition, facts)
    return value, missing


def parse_rule_pack(text: str, *, origin: str = "rule pack") -> RulePack:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RulePackError(f"{origin}: not valid YAML") from exc
    if not isinstance(data, dict):
        raise RulePackError(f"{origin}: expected a mapping at the top level")
    try:
        return RulePack.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise RulePackError(f"{origin}: {problems}") from exc


def load_rule_pack(path: Path) -> RulePack:
    """Load and validate a rule pack file. Raises ``RulePackError``."""
    if not path.is_file():
        raise RulePackError(f"rule pack not found: {path}")
    return parse_rule_pack(path.read_text(encoding="utf-8"), origin=str(path))


def packaged_versions(pack: str) -> list[str]:
    """Versions of a pack shipped with this package, oldest first."""
    directory = resources.files(_PACKAGED).joinpath(pack)
    if not directory.is_dir():
        return []
    return sorted(
        entry.name for entry in directory.iterdir() if entry.joinpath(PACK_FILE).is_file()
    )


def load_packaged_pack(pack: str, version: str | None = None) -> RulePack:
    """Load a pack shipped with the package; the newest version unless one is named."""
    versions = packaged_versions(pack)
    if not versions:
        raise RulePackError(f"no rule pack named '{pack}' is shipped with this version")
    chosen = versions[-1] if version is None else version
    if chosen not in versions:
        raise RulePackError(
            f"rule pack '{pack}' has no version '{chosen}' (available: {', '.join(versions)})"
        )
    resource = resources.files(_PACKAGED).joinpath(pack, chosen, PACK_FILE)
    return parse_rule_pack(resource.read_text(encoding="utf-8"), origin=f"{pack}/{chosen}")
