import re
from datetime import UTC, date, datetime
from decimal import Decimal
from importlib import resources

import pytest
import yaml

from ai_arbiter.core.i18n import SUPPORTED_LOCALES, LocalisationError, Translator, negotiate
from ai_arbiter.core.rules import load_packaged_pack


def catalogue(locale: str) -> dict[str, str]:
    path = resources.files("ai_arbiter").joinpath("locales", f"{locale}.yaml")
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")))


def test_every_locale_has_the_same_keys() -> None:
    english = catalogue("en")

    for locale in SUPPORTED_LOCALES:
        assert set(catalogue(locale)) == set(english), locale


def test_every_locale_uses_the_same_placeholders() -> None:
    english = catalogue("en")

    for locale in SUPPORTED_LOCALES:
        for key, message in catalogue(locale).items():
            assert set(re.findall(r"{(\w+)}", message)) == set(
                re.findall(r"{(\w+)}", english[key])
            ), f"{locale}: {key}"


def test_every_locale_states_that_arbiter_is_not_legal_advice() -> None:
    assert "legal advice" in Translator("en").text("disclaimer")
    assert "consulenza legale" in Translator("it").text("disclaimer")


def test_no_message_claims_compliance() -> None:
    """Outputs say "indicative" and "no findings", never that something is compliant.

    The legal terms "conformity assessment" and "in accordance with" are not such a
    claim; in Italian they share a root with "conforme", hence the whole-word match.
    """
    claim = re.compile(r"\b(compliant|non-compliant|conforme|conformi)\b", re.IGNORECASE)

    for locale in SUPPORTED_LOCALES:
        for key, message in catalogue(locale).items():
            assert not claim.search(message), f"{locale}: {key}"


def test_messages_of_the_default_policy_pack_exist_in_every_locale() -> None:
    keys = {rule.then.message_key for rule in load_packaged_pack("policy").rules}

    for locale in SUPPORTED_LOCALES:
        assert all(Translator(locale).has(key) for key in keys), locale


def test_text_fills_placeholders() -> None:
    assert Translator("en").text("usage.period_value", start="A", end="B") == "A to B"
    assert Translator("it").text("usage.period_value", start="A", end="B") == "dal A al B"


def test_numbers_and_dates_follow_the_locale() -> None:
    english, italian = Translator("en"), Translator("it")

    assert english.integer(1234567) == "1,234,567"
    assert italian.integer(1234567) == "1.234.567"
    assert english.amount(Decimal("1234.5")) == "1,234.500000"
    assert italian.amount(Decimal("1234.5")) == "1.234,500000"
    assert italian.decimal(Decimal("0.92")) == "0,92"
    assert english.date(date(2026, 10, 2)) == "October 2, 2026"
    assert italian.date(date(2026, 10, 2)) == "2 ottobre 2026"
    assert "2026" in italian.timestamp(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))


def test_an_unsupported_locale_or_a_missing_message_is_an_error() -> None:
    with pytest.raises(LocalisationError, match="unsupported locale 'fr'"):
        Translator("fr")
    with pytest.raises(LocalisationError, match="no message 'nope'"):
        Translator("en").text("nope")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("it-IT,it;q=0.9,en;q=0.8", "it"),
        ("fr-FR,it;q=0.5", "it"),
        ("de", "en"),
        ("EN-gb", "en"),
    ],
)
def test_locale_negotiation(header: str | None, expected: str) -> None:
    assert negotiate(header) == expected
