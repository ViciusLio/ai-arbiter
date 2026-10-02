"""Declarative rule engine shared by policy, classification and scanning (ADR-0012)."""

from ai_arbiter.core.rules.decision import ENGINE_VERSION, Decision, DecisionKind, facts_digest
from ai_arbiter.core.rules.engine import (
    ConditionTrace,
    Facts,
    FactValue,
    RuleEvaluationError,
    RuleMatch,
    RulePackError,
    evaluate,
    load_packaged_pack,
    load_rule_pack,
    packaged_versions,
    parse_rule_pack,
)
from ai_arbiter.core.rules.schema import FactType, LegalRef, Rule, RuleKind, RulePack

__all__ = [
    "ENGINE_VERSION",
    "ConditionTrace",
    "Decision",
    "DecisionKind",
    "FactType",
    "FactValue",
    "Facts",
    "LegalRef",
    "Rule",
    "RuleEvaluationError",
    "RuleKind",
    "RuleMatch",
    "RulePack",
    "RulePackError",
    "evaluate",
    "facts_digest",
    "load_packaged_pack",
    "load_rule_pack",
    "packaged_versions",
    "parse_rule_pack",
]
