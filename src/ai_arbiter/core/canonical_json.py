"""Canonical JSON: RFC 8785 (JCS) for values without floating-point numbers (ADR-0029).

The bytes returned here are what gets hashed for audit entries and decision inputs. For
the types accepted, the output is exactly what any RFC 8785 implementation produces, so a
third party can recompute a hash with a library of their choice.
"""

import hashlib
from collections.abc import Mapping, Sequence

from ai_arbiter.core.errors import ArbiterError

type JsonValue = bool | int | str | Sequence[JsonValue] | Mapping[str, JsonValue] | None

# Largest magnitude a JSON number represents exactly (IEEE 754 double), per RFC 8785.
MAX_SAFE_INTEGER = 2**53 - 1

_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


class CanonicalizationError(ArbiterError, ValueError):
    """The value cannot be written as canonical JSON."""


def _string(value: str) -> str:
    parts = ['"']
    for character in value:
        code = ord(character)
        if code in _ESCAPES:
            parts.append(_ESCAPES[code])
        elif code < 0x20:
            parts.append(f"\\u{code:04x}")
        elif 0xD800 <= code <= 0xDFFF:
            raise CanonicalizationError("string contains a lone surrogate")
        else:
            parts.append(character)
    parts.append('"')
    return "".join(parts)


def _utf16_order(key: str) -> bytes:
    # RFC 8785 sorts property names by UTF-16 code units, which differs from code point
    # order for characters outside the Basic Multilingual Plane.
    return key.encode("utf-16-be", "surrogatepass")


def _serialize(value: object) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalizationError("integer is outside the range JSON represents exactly")
        return str(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalizationError("object keys must be strings")
        members = (
            f"{_string(key)}:{_serialize(value[key])}" for key in sorted(value, key=_utf16_order)
        )
        return "{" + ",".join(members) + "}"
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, float):
        raise CanonicalizationError(
            "floating-point numbers are not supported; use an integer or a decimal string"
        )
    raise CanonicalizationError(f"unsupported type: {type(value).__name__}")


def canonicalize(value: object) -> bytes:
    """Return the RFC 8785 form of ``value`` as UTF-8 bytes.

    Accepts ``None``, booleans, integers, strings, sequences and mappings with string
    keys. Raises ``CanonicalizationError`` for anything else, floats included.
    """
    return _serialize(value).encode("utf-8")


def sha256_hex(value: object) -> str:
    """SHA-256 of the canonical form, in hexadecimal."""
    return hashlib.sha256(canonicalize(value)).hexdigest()
