"""The decision envelope: one shape for every automated outcome.

A decision says what was decided, by which rules of which pack version, and carries a
digest of the facts it was decided on. The facts themselves are not kept.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ai_arbiter.core.canonical_json import JsonValue, sha256_hex
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import utcnow
from ai_arbiter.core.rules.engine import Facts, RuleMatch

ENGINE_VERSION = "1"


class DecisionKind(StrEnum):
    POLICY = "policy"
    ROUTING = "routing"
    BUDGET = "budget"
    CLASSIFICATION = "classification"
    FINDING = "finding"


def facts_digest(facts: Facts) -> str:
    """SHA-256 over the canonical JSON of the facts."""
    return sha256_hex({name: _plain(value) for name, value in facts.items()})


def _plain(value: Any) -> Any:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return value
    return list(value)


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=new_id)
    kind: DecisionKind
    outcome: str
    matches: tuple[RuleMatch, ...] = ()
    input_digest: str
    engine_version: str = ENGINE_VERSION
    decided_at: datetime = Field(default_factory=utcnow)
    # Structured explanation that is not a rule match, for example a route plan.
    # Identifiers and names only, never content.
    details: Mapping[str, JsonValue] = Field(default_factory=dict)

    def audit_payload(self) -> dict[str, JsonValue]:
        """What the audit log stores: JSON without floats, ready to be canonicalised."""
        return {
            "id": str(self.id),
            "kind": self.kind.value,
            "outcome": self.outcome,
            "input_digest": self.input_digest,
            "engine_version": self.engine_version,
            "matches": [
                {
                    "rule_id": match.rule_id,
                    "pack": match.pack,
                    "pack_version": match.pack_version,
                    "outcome": match.outcome,
                    "message_key": match.message_key,
                    "applies_from": (
                        match.applies_from.isoformat() if match.applies_from else None
                    ),
                    "legal_refs": [
                        {"regulation": ref.regulation, "article": ref.article}
                        for ref in match.legal_refs
                    ],
                    "matched": [
                        {
                            "fact": trace.fact,
                            "operator": trace.operator,
                            "expected": trace.expected,
                            "negated": trace.negated,
                        }
                        for trace in match.matched
                    ],
                }
                for match in self.matches
            ],
            "details": dict(self.details),
        }
