import json
import random
import string

import pytest
import rfc8785

from ai_arbiter.core.canonical_json import (
    MAX_SAFE_INTEGER,
    CanonicalizationError,
    canonicalize,
    sha256_hex,
)


def test_literals_and_integers() -> None:
    assert canonicalize(None) == b"null"
    assert canonicalize(True) == b"true"
    assert canonicalize(False) == b"false"
    assert canonicalize(0) == b"0"
    assert canonicalize(-42) == b"-42"
    assert canonicalize(MAX_SAFE_INTEGER) == b"9007199254740991"


def test_no_whitespace_and_keys_sorted() -> None:
    assert canonicalize({"b": [1, 2], "a": {"d": None, "c": True}}) == (
        b'{"a":{"c":true,"d":null},"b":[1,2]}'
    )


def test_string_escapes_follow_the_rfc() -> None:
    # RFC 8785, section 3.2.2.2: the short escapes, lowercase \u00xx for other control
    # characters, everything else as is.
    value = '\u20ac$\u000f\nA\'B"\\\\"/'

    assert canonicalize(value) == '"\u20ac$\\u000f\\nA\'B\\"\\\\\\\\\\"/"'.encode()
    assert canonicalize("\b\t\n\f\r") == b'"\\b\\t\\n\\f\\r"'
    assert canonicalize("\u007f") == b'"\x7f"'


def test_keys_are_sorted_by_utf16_code_units() -> None:
    # RFC 8785, section 3.2.3. U+1F600 is encoded as the surrogate pair D83D DE00, which
    # sorts before U+FB33 in UTF-16 and after it by code point.
    value = {
        "\u20ac": "Euro Sign",
        "\r": "Carriage Return",
        "\ufb33": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "\U0001f600": "Emoji: Grinning Face",
        "\u0080": "Control",
        "\u00f6": "Latin Small Letter O With Diaeresis",
    }

    keys = list(json.loads(canonicalize(value)))

    assert keys == ["\r", "1", "\u0080", "\u00f6", "\u20ac", "\U0001f600", "\ufb33"]


def test_tuples_are_arrays() -> None:
    assert canonicalize(("a", 1)) == b'["a",1]'


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (1.5, "floating-point"),
        ({"a": 0.1}, "floating-point"),
        (MAX_SAFE_INTEGER + 1, "outside the range"),
        (-(MAX_SAFE_INTEGER + 1), "outside the range"),
        ({1: "a"}, "keys must be strings"),
        ("\ud800", "lone surrogate"),
        (b"bytes", "unsupported type: bytes"),
        ({"a": {1, 2}}, "unsupported type: set"),
    ],
)
def test_values_outside_the_supported_subset_are_refused(value: object, message: str) -> None:
    with pytest.raises(CanonicalizationError, match=message):
        canonicalize(value)


def test_the_digest_does_not_depend_on_key_order() -> None:
    assert sha256_hex({"a": 1, "b": 2}) == sha256_hex({"b": 2, "a": 1})
    assert sha256_hex({"a": 1}) != sha256_hex({"a": 2})


def _random_value(rng: random.Random, depth: int = 0) -> object:
    alphabet = string.printable + "\u00e8\u00f6\u20ac\u4e2d\U0001f600\ufb33\u0001\u001f\u007f\u2028"
    kind = rng.randrange(7 if depth < 4 else 5)
    if kind == 0:
        return None
    if kind == 1:
        return rng.choice([True, False])
    if kind == 2:
        return rng.choice([0, -1, 1, MAX_SAFE_INTEGER, -MAX_SAFE_INTEGER, rng.randrange(10**12)])
    if kind in (3, 4):
        return "".join(rng.choice(alphabet) for _ in range(rng.randrange(12)))
    if kind == 5:
        return [_random_value(rng, depth + 1) for _ in range(rng.randrange(5))]
    return {
        "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 6))): _random_value(
            rng, depth + 1
        )
        for _ in range(rng.randrange(5))
    }


def test_output_equals_an_independent_rfc8785_implementation() -> None:
    rng = random.Random(8785)  # noqa: S311 - test data, not a secret

    for _ in range(500):
        value = _random_value(rng)
        assert canonicalize(value) == rfc8785.dumps(value)  # type: ignore[arg-type]
