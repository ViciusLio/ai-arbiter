"""PII detection and redaction (ADR-0014, ADR-0027)."""

from ai_arbiter.core.redaction.builtin import GENERAL_LIMITS, BuiltinDetector
from ai_arbiter.core.redaction.model import DetectorInfo, PIIDetector, PIISpan
from ai_arbiter.core.redaction.redact import (
    RedactionStrategy,
    categories,
    derive_key,
    keyed_digest,
    redact,
)

__all__ = [
    "GENERAL_LIMITS",
    "BuiltinDetector",
    "DetectorInfo",
    "PIIDetector",
    "PIISpan",
    "RedactionStrategy",
    "categories",
    "derive_key",
    "keyed_digest",
    "redact",
]
