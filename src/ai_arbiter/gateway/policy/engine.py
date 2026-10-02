"""Pre-call policy evaluation (ADR-0012).

Code computes the facts; the rule pack, which is data, decides. When several rules match,
the strongest outcome wins and every match stays in the decision.
"""

from collections.abc import Collection, Sequence
from enum import StrEnum

from ai_arbiter.core.config.settings import PolicySettings
from ai_arbiter.core.ports.llm import ChatRequest
from ai_arbiter.core.rules import (
    Decision,
    DecisionKind,
    Facts,
    RuleKind,
    RulePack,
    evaluate,
    facts_digest,
    load_packaged_pack,
    load_rule_pack,
)
from ai_arbiter.gateway.finops.budgets import BudgetStatus

POLICY_PACK = "policy"


class PolicyOutcome(StrEnum):
    ALLOW = "allow"
    REDACT = "redact"
    DENY = "deny"


# Strongest first. An outcome a custom pack invents is treated as the weakest.
_STRENGTH = (PolicyOutcome.DENY.value, PolicyOutcome.REDACT.value, PolicyOutcome.ALLOW.value)


def load_policy_pack(settings: PolicySettings) -> RulePack:
    if settings.pack is not None:
        return load_rule_pack(settings.pack)
    return load_packaged_pack(POLICY_PACK)


def collect_facts(
    request: ChatRequest,
    *,
    allowed_models: Collection[str] | None,
    budget: BudgetStatus,
    pii_categories: Sequence[str],
    system_declared: bool,
) -> Facts:
    """Facts for the pre-call evaluation. Names and types match the policy pack."""
    return {
        "request.model": request.model,
        "request.model_allowed": allowed_models is None or request.model in allowed_models,
        "request.stream": request.stream,
        "budget.hard_exceeded": budget.hard_exceeded,
        "budget.soft_exceeded": budget.soft_exceeded,
        "pii.detected": bool(pii_categories),
        "pii.categories": list(pii_categories),
        "system.declared": system_declared,
    }


class RulePolicyEngine:
    """Default implementation of the ``PolicyEngine`` port: delegates to ``core.rules``."""

    def __init__(self, pack: RulePack) -> None:
        self.pack = pack

    async def evaluate(self, stage: str, facts: Facts) -> Decision:
        matches = evaluate(self.pack, RuleKind.POLICY, facts) if stage == "pre_call" else []
        outcomes = {match.outcome for match in matches}
        outcome = next(
            (candidate for candidate in _STRENGTH if candidate in outcomes),
            PolicyOutcome.ALLOW.value,
        )
        return Decision(
            kind=DecisionKind.POLICY,
            outcome=outcome,
            matches=tuple(matches),
            input_digest=facts_digest(facts),
            details={"stage": stage, "pack": self.pack.pack, "pack_version": self.pack.version},
        )
