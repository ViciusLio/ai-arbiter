"""Classification as a pure function of a rule pack, declared facts and roles."""

from collections.abc import Collection, Mapping, Sequence
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict

from ai_arbiter.core.canonical_json import sha256_hex
from ai_arbiter.core.domain.risk import TIER_SEVERITY, ActorRole, RiskTier
from ai_arbiter.core.rules import (
    Decision,
    DecisionKind,
    Facts,
    RuleKind,
    RuleMatch,
    RulePack,
    condition_state,
    evaluate_partial,
)

OBLIGATION = "obligation"
# The roles whose obligations this version evaluates (ADR-0007). Other roles are stored
# and reported as not covered.
COVERED_ROLES = frozenset({ActorRole.DEPLOYER})


class Obligation(BaseModel):
    """Something that follows from the classification, with where it comes from."""

    model_config = ConfigDict(frozen=True)

    id: str
    outcome: str
    message_key: str
    legal_refs: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    applies_from: date | None = None
    # Whether the organisation holds one of the roles the obligation is addressed to.
    applies_to_declared_roles: bool = True

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "outcome": self.outcome,
            "message_key": self.message_key,
            "legal_refs": list(self.legal_refs),
            "roles": list(self.roles),
            "applies_from": self.applies_from.isoformat() if self.applies_from else None,
            "applies_to_declared_roles": self.applies_to_declared_roles,
        }


class ClassificationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    tier: RiskTier
    obligations: tuple[Obligation, ...]
    matches: tuple[RuleMatch, ...]
    # Facts to ask for next. Empty when nothing more could change the result.
    missing_facts: tuple[str, ...]
    roles_not_covered: tuple[str, ...]
    decision: Decision

    @property
    def complete(self) -> bool:
        return not self.missing_facts


def _severity(outcome: str) -> int:
    """Position on the scale, lower being more severe; unknown outcomes are the least."""
    for position, tier in enumerate(TIER_SEVERITY):
        if tier.value == outcome:
            return position
    return len(TIER_SEVERITY)


def _addressed(roles: Sequence[str], declared: Collection[ActorRole]) -> bool:
    return not roles or bool({role.value for role in declared} & set(roles))


def input_digest(pack: RulePack, facts: Facts, roles: Collection[ActorRole]) -> str:
    relevant = {name: _plain(value) for name, value in facts.items() if name in pack.facts}
    return sha256_hex(
        {
            "pack": pack.pack,
            "version": pack.version,
            "roles": sorted(role.value for role in roles),
            "facts": relevant,
        }
    )


def _plain(value: Any) -> Any:
    return list(value) if isinstance(value, list | tuple) else value


def classify(pack: RulePack, facts: Facts, roles: Collection[ActorRole]) -> ClassificationResult:
    """Indicative tier and obligations for a system.

    The tier is the most severe outcome among the rules that hold. When a rule that
    cannot be told yet could give a more severe outcome, the tier is ``undetermined``
    and the facts to ask for are listed: an unanswered question is never read as "no"
    (ADR-0035).
    """
    known: Facts = {name: value for name, value in facts.items() if name in pack.facts}
    evaluation = evaluate_partial(pack, RuleKind.CLASSIFICATION, known)
    matches = evaluation.matches
    out_of_scope = [m for m in matches if m.outcome == RiskTier.OUT_OF_SCOPE.value]
    missing: dict[str, None] = {}
    obligations: list[Obligation] = []

    if out_of_scope:
        tier = RiskTier.OUT_OF_SCOPE
        matches = tuple(out_of_scope)
    else:
        for name in evaluation.missing_facts:
            missing.setdefault(name)
        scope_open = any(rule.outcome == RiskTier.OUT_OF_SCOPE.value for rule in evaluation.open)
        held = min((_severity(m.outcome) for m in matches), default=len(TIER_SEVERITY))
        held = min(held, _severity(RiskTier.MINIMAL.value))
        worse_open = any(
            _severity(rule.outcome) < held
            for rule in evaluation.open
            if rule.outcome != RiskTier.OUT_OF_SCOPE.value
        )
        tier = RiskTier.UNDETERMINED if scope_open or worse_open else TIER_SEVERITY[held]

        for match in matches:
            obligations.append(
                Obligation(
                    id=match.rule_id,
                    outcome=match.outcome,
                    message_key=match.message_key,
                    legal_refs=tuple(ref.article for ref in match.legal_refs),
                    roles=match.roles,
                    applies_from=match.applies_from,
                    applies_to_declared_roles=_addressed(match.roles, roles),
                )
            )
        tier_dates = [m.applies_from for m in matches if m.outcome == tier.value and m.applies_from]
        for extra in pack.outcome_obligations:
            if extra.outcome != tier.value:
                continue
            value, needs = (True, []) if extra.when is None else condition_state(extra.when, known)
            for name in needs:
                missing.setdefault(name)
            if value:
                obligations.append(
                    Obligation(
                        id=extra.id,
                        outcome=OBLIGATION,
                        message_key=extra.message_key,
                        legal_refs=tuple(ref.article for ref in extra.legal_refs),
                        roles=extra.roles,
                        applies_from=extra.applies_from or min(tier_dates, default=None),
                        applies_to_declared_roles=_addressed(extra.roles, roles),
                    )
                )

    uncovered = tuple(sorted(role.value for role in roles if role not in COVERED_ROLES))
    review = pack.regulation.review if pack.regulation else None
    decision = Decision(
        kind=DecisionKind.CLASSIFICATION,
        outcome=f"tier:{tier.value}",
        matches=matches,
        input_digest=input_digest(pack, known, roles),
        details={
            "pack": pack.pack,
            "pack_version": pack.version,
            "pack_review": review,
            "missing_facts": list(missing),
            "roles": sorted(role.value for role in roles),
            "roles_not_covered": list(uncovered),
            "obligations": [obligation.id for obligation in obligations],
        },
    )
    return ClassificationResult(
        tier=tier,
        obligations=tuple(obligations),
        matches=matches,
        missing_facts=tuple(missing),
        roles_not_covered=uncovered,
        decision=decision,
    )


def ordered_questions(pack: RulePack, names: Sequence[str]) -> list[str]:
    """Facts in questionnaire order: by stage, then as the pack declares them."""
    stage_order: Mapping[str | None, int] = {stage: i for i, stage in enumerate(pack.stages)}
    declared = list(pack.facts)
    return sorted(
        names,
        key=lambda name: (
            stage_order.get(pack.facts[name].stage, len(stage_order)),
            declared.index(name),
        ),
    )
