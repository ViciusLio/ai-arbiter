import pytest

from ai_arbiter.core.config import RedactionSettings
from ai_arbiter.core.redaction import (
    GENERAL_LIMITS,
    BuiltinDetector,
    PIISpan,
    RedactionStrategy,
    categories,
    derive_key,
    redact,
)
from ai_arbiter.core.redaction.builtin import (
    IBAN_LENGTHS,
    fiscal_code_is_valid,
    iban_is_valid,
    luhn_is_valid,
    vat_number_is_valid,
)
from ai_arbiter.gateway.identity.keys import generate_key

detector = BuiltinDetector()

# Assembled from parts so that secret scanners do not mistake the fixtures for real ones.
JWT = ".".join(["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0NSJ9", "dBjftJeZ4CVPmB92K27uhbUJU1p1r"])
AWS_KEY_ID = "AKIA" + "IOSFODNN7EXAMPLE"
_DASHES = "-" * 5
PEM = f"{_DASHES}BEGIN RSA PRIVATE KEY{_DASHES}\nMIIabc\n{_DASHES}END RSA PRIVATE KEY{_DASHES}"


def found(text: str) -> list[tuple[str, str]]:
    return [(span.category, text[span.start : span.end]) for span in detector.detect(text)]


# Values that are publicly documented examples or test numbers, not anybody's data.
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "write to mario.rossi+news@example.co.uk today",
            [("email", "mario.rossi+news@example.co.uk")],
        ),
        ("<a@b.io>", [("email", "a@b.io")]),
        ("call +39 347 1234567 now", [("phone", "+39 347 1234567")]),
        ("call +393471234567.", [("phone", "+393471234567")]),
        ("US: +1 (415) 555-2671", [("phone", "+1 (415) 555-2671")]),
        ("cell 347 1234567", [("phone", "347 1234567")]),
        ("il mio numero: 3471234567", [("phone", "3471234567")]),
        ("tel. 02 12345678", [("phone", "02 12345678")]),
        ("Telefono ufficio 06-1234567", [("phone", "06-1234567")]),
        ("IBAN IT60X0542811101000000123456", [("iban", "IT60X0542811101000000123456")]),
        (
            "pay to IT60 X054 2811 1010 0000 0123 456, thanks",
            [("iban", "IT60 X054 2811 1010 0000 0123 456")],
        ),
        ("DE89370400440532013000", [("iban", "DE89370400440532013000")]),
        ("card 4111 1111 1111 1111 exp 12/29", [("payment_card", "4111 1111 1111 1111")]),
        ("5555-5555-5555-4444", [("payment_card", "5555-5555-5555-4444")]),
        ("amex 378282246310005", [("payment_card", "378282246310005")]),
        ("CF: RSSMRA85T10A562S", [("it_fiscal_code", "RSSMRA85T10A562S")]),
        ("codice rssmra85t10a562s.", [("it_fiscal_code", "rssmra85t10a562s")]),
        ("P.IVA 00743110157", [("it_vat_number", "00743110157")]),
        ("partita IVA: 12345678903", [("it_vat_number", "12345678903")]),
        ("VAT IT12345678903", [("it_vat_number", "IT12345678903")]),
        ("server 192.168.1.10 is down", [("ip_address", "192.168.1.10")]),
        (
            "from 2001:db8::8a2e:370:7334 to ::1",
            [("ip_address", "2001:db8::8a2e:370:7334"), ("ip_address", "::1")],
        ),
        (f"key {AWS_KEY_ID}", [("secret", AWS_KEY_ID)]),
        ("token ghp_" + "a1B2" * 9, [("secret", "ghp_" + "a1B2" * 9)]),
        ("sk-" + "abcd1234" * 4, [("secret", "sk-" + "abcd1234" * 4)]),
        (f"key:\n{PEM}\nend", [("secret", PEM)]),
        (f"jwt {JWT}", [("secret", JWT)]),
    ],
)
def test_detects(text: str, expected: list[tuple[str, str]]) -> None:
    assert found(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "no personal data here, just words and the number 42",
        "not an address: user@localhost or @handle or a@b",
        "order 1234567890123456 was shipped",  # 16 digits that fail the Luhn check
        "4111 1111 1111 1112",  # card with a wrong check digit
        "1111 1111 1111 1111",  # passes no network prefix
        "IT60X0542811101000000123457",  # IBAN with a wrong check
        "XX60X0542811101000000123456",  # unknown country
        "IT60X05428111010000001234567",  # one character too long
        "RSSMRA85T10A562T",  # fiscal code with a wrong check character
        "the code 12345678903 on the label",  # valid check digit, nothing says it is a VAT number
        "P.IVA 12345678901",  # wrong check digit
        "ring 02 12345678 for pizza",  # landline without a word that says it is a phone
        "total 3471234567.50 EUR",  # an amount, not a mobile number
        "version 300.1.2.3 and 1.2.3",  # not an IPv4 address
        "at 12:30:45 sharp",  # a time, not IPv6
        "010.001.001.001",  # leading zeros
        "sk-short",
        "it costs +39 euro",
        "ref +1234",
    ],
)
def test_does_not_detect(text: str) -> None:
    assert found(text) == []


def test_arbiters_own_keys_are_detected_as_secrets() -> None:
    key = generate_key().plaintext

    assert found(f"my key is {key}!") == [("secret", key)]


def test_several_things_in_one_text_are_reported_in_order() -> None:
    text = "Mario (mario@example.com, +39 347 1234567) IBAN IT60X0542811101000000123456"

    assert [category for category, _ in found(text)] == ["email", "phone", "iban"]


def test_overlapping_matches_keep_the_most_certain_one() -> None:
    # The digits of an IBAN can look like a phone or a card number.
    text = "IT60X0542811101000000123456"

    assert found(text) == [("iban", text)]


def test_spans_carry_positions_and_confidence_but_no_text() -> None:
    span = detector.detect("mail a@b.io")[0]

    assert (span.start, span.end, span.category) == (5, 11, "email")
    assert 0 < span.confidence <= 1
    assert "a@b.io" not in repr(span)


def test_checksum_functions() -> None:
    assert iban_is_valid("GB82WEST12345698765432")
    assert not iban_is_valid("GB82WEST1234569876543")
    assert fiscal_code_is_valid("MRTMTT91D08F205J")
    assert not fiscal_code_is_valid("MRTMTT91D08F205")
    assert not fiscal_code_is_valid("MRTMTT91D08F205!")
    assert vat_number_is_valid("00743110157")
    assert not vat_number_is_valid("00000000000")
    assert luhn_is_valid("4111111111111111")
    assert IBAN_LENGTHS["IT"] == 27


def test_every_category_says_what_it_validates_and_what_it_misses() -> None:
    described = detector.describe()

    assert [info.category for info in described] == [
        "email",
        "phone",
        "iban",
        "payment_card",
        "it_fiscal_code",
        "it_vat_number",
        "ip_address",
        "secret",
    ]
    assert all(len(info.validates) > 20 and len(info.misses) > 20 for info in described)
    assert "do not detect names" in GENERAL_LIMITS


TEXT = "mail mario@example.com or call +39 347 1234567"


def test_mask_replaces_each_value_with_its_category() -> None:
    assert redact(TEXT, detector.detect(TEXT)) == "mail [EMAIL] or call [PHONE]"


def test_drop_removes_the_value() -> None:
    result = redact(TEXT, detector.detect(TEXT), default=RedactionStrategy.DROP)

    assert result == "mail  or call "


def test_strategies_are_chosen_per_category() -> None:
    result = redact(
        TEXT,
        detector.detect(TEXT),
        strategies={"phone": RedactionStrategy.DROP},
        default=RedactionStrategy.MASK,
    )

    assert result == "mail [EMAIL] or call "


def test_hash_gives_the_same_tag_for_the_same_value_and_key() -> None:
    key = derive_key(b"root-secret", "redaction", "tenant-a")
    spans = detector.detect(TEXT)

    first = redact(TEXT, spans, default=RedactionStrategy.HASH, key=key)
    again = redact(TEXT, spans, default=RedactionStrategy.HASH, key=key)
    other_tenant = redact(
        TEXT,
        spans,
        default=RedactionStrategy.HASH,
        key=derive_key(b"root-secret", "redaction", "tenant-b"),
    )

    assert first == again
    assert first != other_tenant
    assert "mario@example.com" not in first
    assert first.startswith("mail [EMAIL:")
    assert len(first.split("[EMAIL:")[1].split("]")[0]) == 8


def test_hash_without_a_key_is_refused() -> None:
    with pytest.raises(ValueError, match="needs a key"):
        redact(TEXT, detector.detect(TEXT), default=RedactionStrategy.HASH)


def test_derived_keys_differ_by_purpose_and_scope() -> None:
    keys = {
        derive_key(b"root", "redaction", "a"),
        derive_key(b"root", "redaction", "b"),
        derive_key(b"root", "fingerprint", "a"),
        derive_key(b"other", "redaction", "a"),
    }

    assert len(keys) == 4


def test_text_without_spans_is_returned_unchanged() -> None:
    assert redact("nothing to see", []) == "nothing to see"


def test_overlapping_spans_given_by_a_plugin_are_replaced_once() -> None:
    spans = [
        PIISpan(category="a", start=0, end=5, confidence=0.9),
        PIISpan(category="b", start=3, end=8, confidence=0.9),
    ]

    assert redact("0123456789", spans) == "[A]56789"


def test_categories_are_unique_and_sorted() -> None:
    assert categories(detector.detect(TEXT + " and luigi@example.com")) == ["email", "phone"]


def test_settings_refuse_the_hash_strategy_without_a_key() -> None:
    with pytest.raises(ValueError, match=r"needs redaction\.key"):
        RedactionSettings(default_strategy="hash")
    with pytest.raises(ValueError, match=r"needs redaction\.key"):
        RedactionSettings(strategies={"email": "hash"})
    with pytest.raises(ValueError, match="not a secret reference"):
        RedactionSettings(key="the-key-itself")

    assert RedactionSettings(default_strategy="hash", key="secret://redaction-key").key
