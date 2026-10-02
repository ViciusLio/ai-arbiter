"""Built-in detectors: patterns backed by a checksum or an unambiguous format.

This is the set of ADR-0027. Each detector rejects most look-alikes by construction, which
is what allows redaction to be on by default. The price is recall: names, addresses,
dates of birth, health data and anything written in free text are not detected. Call
``describe`` (or run ``arbiter pii detectors``) for the list of what each detector
validates and misses.
"""

import ipaddress
import re
from collections.abc import Callable, Iterator, Sequence

from ai_arbiter.core.redaction.model import DetectorInfo, PIISpan

Finder = Callable[[str], Iterator[PIISpan]]

# --- email -------------------------------------------------------------------------------

_EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}(?![A-Za-z0-9-])"
)


def _emails(text: str) -> Iterator[PIISpan]:
    for match in _EMAIL.finditer(text):
        yield PIISpan(category="email", start=match.start(), end=match.end(), confidence=0.95)


# --- phone -------------------------------------------------------------------------------

_E164 = re.compile(r"(?<![\w+])\+[1-9](?:[ .\-]?\(?\d\)?){6,14}(?!\d)")
_IT_MOBILE = re.compile(r"(?<![\w+.,\-/])3[1-9]\d[ .\-]?\d{3}[ .\-]?\d{3,4}(?![\w\-/]|[.,]\d)")
_IT_LANDLINE = re.compile(r"(?<![\w+.,\-/])0\d{1,3}[ .\-/]?\d{5,8}(?![\w\-/]|[.,]\d)")
_PHONE_CONTEXT = re.compile(
    r"\b(?:tel|telefono|fax|cell|cellulare|phone|mobile|numero|chiama\w*)\b[^\n]{0,20}$",
    re.IGNORECASE,
)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def _phones(text: str) -> Iterator[PIISpan]:
    for match in _E164.finditer(text):
        if 7 <= len(_digits(match.group())) <= 15:
            yield PIISpan(category="phone", start=match.start(), end=match.end(), confidence=0.85)
    for match in _IT_MOBILE.finditer(text):
        if len(_digits(match.group())) in (9, 10):
            yield PIISpan(category="phone", start=match.start(), end=match.end(), confidence=0.6)
    for match in _IT_LANDLINE.finditer(text):
        # A bare number starting with 0 is too common: require a word that says it is one.
        if 6 <= len(_digits(match.group())) <= 11 and _PHONE_CONTEXT.search(
            text[max(0, match.start() - 40) : match.start()]
        ):
            yield PIISpan(category="phone", start=match.start(), end=match.end(), confidence=0.6)


# --- IBAN --------------------------------------------------------------------------------

# Length of the IBAN in each country of the SEPA area.
IBAN_LENGTHS = {
    "AD": 24, "AL": 28, "AT": 20, "BE": 16, "BG": 22, "CH": 21, "CY": 28, "CZ": 24,
    "DE": 22, "DK": 18, "EE": 20, "ES": 24, "FI": 18, "FR": 27, "GB": 22, "GI": 23,
    "GR": 27, "HR": 21, "HU": 28, "IE": 22, "IS": 26, "IT": 27, "LI": 21, "LT": 20,
    "LU": 20, "LV": 21, "MC": 27, "MD": 24, "ME": 22, "MK": 19, "MT": 31, "NL": 18,
    "NO": 15, "PL": 28, "PT": 25, "RO": 24, "RS": 22, "SE": 24, "SI": 19, "SK": 24,
    "SM": 27, "VA": 22,
}  # fmt: skip
_IBAN_START = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}\d{2}")


def iban_is_valid(iban: str) -> bool:
    """ISO 13616: right length for the country and mod-97 remainder of 1."""
    if len(iban) != IBAN_LENGTHS.get(iban[:2], -1) or not iban.isalnum():
        return False
    rearranged = iban[4:] + iban[:4]
    return int("".join(str(int(character, 36)) for character in rearranged)) % 97 == 1


def _ibans(text: str) -> Iterator[PIISpan]:
    for match in _IBAN_START.finditer(text):
        length = IBAN_LENGTHS.get(match.group()[:2])
        if length is None:
            continue
        # Collect the characters of the IBAN, allowing one space between groups.
        collected: list[str] = []
        position = match.start()
        while position < len(text) and len(collected) < length:
            character = text[position]
            if character.isascii() and character.isalnum():
                collected.append(character.upper())
            elif character != " " or (position > 0 and text[position - 1] == " "):
                break
            position += 1
        followed = position < len(text) and text[position].isascii() and text[position].isalnum()
        if len(collected) == length and not followed and iban_is_valid("".join(collected)):
            yield PIISpan(category="iban", start=match.start(), end=position, confidence=0.99)


# --- payment card ------------------------------------------------------------------------

_CARD = re.compile(r"(?<![\w.,\-/])[2-6]\d{3}(?:[ \-]?\d{4}){2}(?:[ \-]?\d{1,7})(?![\w\-/]|[.,]\d)")


def luhn_is_valid(digits: str) -> bool:
    total = 0
    for index, character in enumerate(reversed(digits)):
        value = int(character)
        if index % 2 == 1:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _cards(text: str) -> Iterator[PIISpan]:
    for match in _CARD.finditer(text):
        digits = _digits(match.group())
        if 13 <= len(digits) <= 19 and len(set(digits)) > 1 and luhn_is_valid(digits):
            yield PIISpan(
                category="payment_card", start=match.start(), end=match.end(), confidence=0.9
            )


# --- Italian fiscal code -----------------------------------------------------------------

_CF = re.compile(
    r"(?<![A-Za-z0-9])[A-Z]{6}[0-9LMNPQRSTUV]{2}[ABCDEHLMPRST][0-9LMNPQRSTUV]{2}"
    r"[A-Z][0-9LMNPQRSTUV]{3}[A-Z](?![A-Za-z0-9])",
    re.IGNORECASE,
)
# Value of a character in an odd position (first, third, ...), per the decree of 1976.
_CF_ODD_VALUES = (
    *(1, 0, 5, 7, 9, 13, 15, 17, 19, 21),  # 0 to 9
    *(1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18),  # A to M
    *(20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23),  # N to Z
)
_CF_ODD = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", _CF_ODD_VALUES, strict=True))


def fiscal_code_is_valid(code: str) -> bool:
    """Check character of a 16-character *codice fiscale* of a natural person."""
    code = code.upper()
    if len(code) != 16 or not code.isalnum():
        return False
    total = 0
    for index, character in enumerate(code[:15]):
        if index % 2 == 0:
            total += _CF_ODD[character]
        else:
            total += int(character) if character.isdigit() else ord(character) - ord("A")
    return code[15] == chr(ord("A") + total % 26)


def _fiscal_codes(text: str) -> Iterator[PIISpan]:
    for match in _CF.finditer(text):
        if fiscal_code_is_valid(match.group()):
            yield PIISpan(
                category="it_fiscal_code", start=match.start(), end=match.end(), confidence=0.99
            )


# --- Italian VAT number ------------------------------------------------------------------

_VAT = re.compile(r"(?<![A-Za-z0-9])(IT[ ]?)?(\d{11})(?![A-Za-z0-9])")
_VAT_CONTEXT = re.compile(
    r"(?:p\.?\s?iva|partita\s+iva|vat(?:\s+(?:no|number|id))?|c\.?\s?f\.?|codice\s+fiscale)"
    r"[^\n]{0,20}$",
    re.IGNORECASE,
)


def vat_number_is_valid(number: str) -> bool:
    """Check digit of an Italian *partita IVA*: eleven digits that satisfy Luhn."""
    return len(number) == 11 and number.isdigit() and number != "0" * 11 and luhn_is_valid(number)


def _vat_numbers(text: str) -> Iterator[PIISpan]:
    for match in _VAT.finditer(text):
        if not vat_number_is_valid(match.group(2)):
            continue
        # One number in ten passes the check by chance: ask for the country prefix or
        # for words that say what the number is.
        if match.group(1) or _VAT_CONTEXT.search(text[max(0, match.start() - 40) : match.start()]):
            yield PIISpan(
                category="it_vat_number", start=match.start(), end=match.end(), confidence=0.9
            )


# --- IP addresses ------------------------------------------------------------------------

_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w]|\.\d)")
_IPV6 = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")


def _ip_addresses(text: str) -> Iterator[PIISpan]:
    for pattern, minimum in ((_IPV4, 7), (_IPV6, 3)):
        for match in pattern.finditer(text):
            candidate = match.group()
            if len(candidate) < minimum or (
                pattern is _IPV4 and re.search(r"(?:^|\.)0\d", candidate)
            ):
                continue
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            yield PIISpan(
                category="ip_address", start=match.start(), end=match.end(), confidence=0.7
            )


# --- secrets -----------------------------------------------------------------------------

_SECRETS = [
    re.compile(
        r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"
        r"(?:[\s\S]*?-----END (?:[A-Z]+ )*PRIVATE KEY-----)?"
    ),
    re.compile(r"(?<![\w-])eyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}(?![A-Za-z0-9])"),
    re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_-]{35}(?![A-Za-z0-9_-])"),
    re.compile(r"(?<![A-Za-z0-9])arb_[a-z0-9]{12}_[0-9A-Za-z]{49}(?![A-Za-z0-9])"),
]


def _secrets(text: str) -> Iterator[PIISpan]:
    for pattern in _SECRETS:
        for match in pattern.finditer(text):
            yield PIISpan(category="secret", start=match.start(), end=match.end(), confidence=0.9)


# --- the detector ------------------------------------------------------------------------

_FINDERS: tuple[tuple[Finder, DetectorInfo], ...] = (
    (
        _emails,
        DetectorInfo(
            category="email",
            validates="Address syntax: local part, domain with at least one dot, top level "
            "made of letters.",
            misses="Addresses written to avoid detection (name at example dot com); "
            "internationalised addresses with non-ASCII characters.",
        ),
    ),
    (
        _phones,
        DetectorInfo(
            category="phone",
            validates="International numbers with a leading + and 7 to 15 digits (E.164); Italian "
            "mobile numbers in national format; Italian landline numbers when a word such as "
            "'tel' or 'telefono' comes before them.",
            misses="National formats of other countries without the + prefix; Italian landline "
            "numbers with no such word nearby; extensions; numbers spelled out in words.",
        ),
    ),
    (
        _ibans,
        DetectorInfo(
            category="iban",
            validates="Country code and length for the countries of the SEPA area, and the "
            "mod-97 check (ISO 13616). Groups of characters may be separated by single spaces.",
            misses="IBANs of countries outside the SEPA area; account numbers in national "
            "formats; IBANs written in lowercase or with other separators.",
        ),
    ),
    (
        _cards,
        DetectorInfo(
            category="payment_card",
            validates="13 to 19 digits starting with 2 to 6, optionally grouped by spaces or "
            "hyphens, that satisfy the Luhn check.",
            misses="Card numbers split across lines or mixed with text; expiry dates and "
            "security codes, which have no checksum.",
        ),
    ),
    (
        _fiscal_codes,
        DetectorInfo(
            category="it_fiscal_code",
            validates="Italian codice fiscale of a natural person: structure of the 16 "
            "characters and the check character, including the letter substitutions used "
            "for homonyms.",
            misses="Codes with a wrong check character (typing errors); the 11-digit fiscal "
            "codes of organisations, which are covered as VAT numbers.",
        ),
    ),
    (
        _vat_numbers,
        DetectorInfo(
            category="it_vat_number",
            validates="Italian partita IVA: 11 digits with a valid check digit, when preceded "
            "by 'IT' or by words such as 'P.IVA', 'partita IVA', 'VAT' or 'codice fiscale'.",
            misses="An 11-digit number with no prefix and no such word nearby; VAT numbers "
            "of other countries.",
        ),
    ),
    (
        _ip_addresses,
        DetectorInfo(
            category="ip_address",
            validates="IPv4 and IPv6 literals that parse as addresses.",
            misses="Host names; addresses with a port or a prefix length attached to an IPv6 "
            "literal. Version numbers with four parts are detected as IPv4 addresses.",
        ),
    ),
    (
        _secrets,
        DetectorInfo(
            category="secret",
            validates="Private key blocks (PEM), JSON Web Tokens, and keys with well-known "
            "prefixes: AWS access key ids, GitHub tokens, 'sk-' API keys, Slack tokens, Google "
            "API keys and Arbiter's own API keys.",
            misses="Passwords and any credential without a recognisable format; secrets of "
            "providers not listed.",
        ),
    ),
)

GENERAL_LIMITS = (
    "The built-in detectors recognise formats, not meaning. They do not detect names, "
    "postal addresses, dates of birth, health data or any personal data written as free "
    "text, and they cover identity documents and the national phone and VAT formats of "
    "other countries only from a later release."
)


def _without_overlaps(spans: list[PIISpan]) -> list[PIISpan]:
    """Keep the most certain span where several cover the same text, then the longest."""
    kept: list[PIISpan] = []
    for span in sorted(spans, key=lambda s: (-s.confidence, -(s.end - s.start), s.start)):
        if all(span.end <= other.start or span.start >= other.end for other in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s.start)


class BuiltinDetector:
    """Registered as ``builtin``. Deterministic, offline, with no dependency."""

    name = "builtin"

    def detect(self, text: str, *, locale: str | None = None) -> Sequence[PIISpan]:
        found = [span for finder, _ in _FINDERS for span in finder(text)]
        return _without_overlaps(found)

    def describe(self) -> Sequence[DetectorInfo]:
        return [info for _, info in _FINDERS]
