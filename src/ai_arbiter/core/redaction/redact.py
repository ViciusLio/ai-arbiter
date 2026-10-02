"""Redaction: replace what the detectors found, by category."""

import hashlib
import hmac
from collections.abc import Mapping, Sequence
from enum import StrEnum

from ai_arbiter.core.redaction.model import PIISpan


class RedactionStrategy(StrEnum):
    MASK = "mask"  # [EMAIL]
    HASH = "hash"  # [EMAIL:1f3a9c2e], the same value always gives the same tag
    DROP = "drop"  # removed


def derive_key(root: bytes, purpose: str, scope: str) -> bytes:
    """A key for one purpose and one scope (a tenant), derived from a root secret.

    Keeps a tag or fingerprint computed for one tenant from being comparable with
    another tenant's, and one use of the root secret from colliding with another.
    """
    return hmac.new(root, f"arbiter/{purpose}/v1/{scope}".encode(), hashlib.sha256).digest()


def keyed_digest(key: bytes, value: str) -> str:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def categories(spans: Sequence[PIISpan]) -> list[str]:
    return sorted({span.category for span in spans})


def redact(
    text: str,
    spans: Sequence[PIISpan],
    *,
    strategies: Mapping[str, RedactionStrategy] | None = None,
    default: RedactionStrategy = RedactionStrategy.MASK,
    key: bytes | None = None,
) -> str:
    """Return ``text`` with every span replaced according to its category's strategy.

    ``hash`` needs ``key``: the tag is a keyed digest, since a plain hash of a phone
    number or a fiscal code can be reversed by trying every possible value.
    """
    strategies = strategies or {}
    result: list[str] = []
    position = 0
    for span in sorted(spans, key=lambda s: s.start):
        if span.start < position:
            continue  # overlaps the previous span, which was already replaced
        result.append(text[position : span.start])
        strategy = strategies.get(span.category, default)
        label = span.category.upper()
        if strategy is RedactionStrategy.MASK:
            result.append(f"[{label}]")
        elif strategy is RedactionStrategy.HASH:
            if key is None:
                raise ValueError("the hash strategy needs a key")
            digest = keyed_digest(key, f"{span.category}:{text[span.start : span.end]}")
            result.append(f"[{label}:{digest[:8]}]")
        position = span.end
    result.append(text[position:])
    return "".join(result)
