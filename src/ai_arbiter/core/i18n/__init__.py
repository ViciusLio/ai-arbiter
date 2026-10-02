"""Localised text for user-facing outputs: keyed YAML catalogues, Babel for formatting
(ADR-0021). English and Italian (ADR-0004)."""

from datetime import date, datetime
from decimal import Decimal
from functools import cache
from importlib import resources
from typing import Any

import yaml
from babel import dates, numbers

from ai_arbiter.core.errors import ArbiterError

DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "it")


class LocalisationError(ArbiterError):
    """A locale is not supported or a message is missing."""


@cache
def _catalogue(locale: str) -> dict[str, str]:
    resource = resources.files("ai_arbiter").joinpath("locales", f"{locale}.yaml")
    data: Any = yaml.safe_load(resource.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in data.items()}


def negotiate(header: str | None) -> str:
    """Pick a supported locale from an ``Accept-Language`` header; English otherwise."""
    for part in (header or "").split(","):
        language = part.split(";")[0].strip().lower().split("-")[0]
        if language in SUPPORTED_LOCALES:
            return language
    return DEFAULT_LOCALE


class Translator:
    def __init__(self, locale: str = DEFAULT_LOCALE) -> None:
        if locale not in SUPPORTED_LOCALES:
            raise LocalisationError(
                f"unsupported locale '{locale}' (supported: {', '.join(SUPPORTED_LOCALES)})"
            )
        self.locale = locale

    def text(self, key: str, **values: object) -> str:
        """The message for ``key``, with ``{placeholders}`` filled in."""
        message = _catalogue(self.locale).get(key)
        if message is None:
            raise LocalisationError(f"no message '{key}' for locale '{self.locale}'")
        return message.format(**values)

    def has(self, key: str) -> bool:
        return key in _catalogue(self.locale)

    def integer(self, value: int) -> str:
        return numbers.format_decimal(value, format="#,##0", locale=self.locale)

    def amount(self, value: Decimal, *, places: int = 4) -> str:
        pattern = "#,##0." + "0" * places
        return numbers.format_decimal(value, format=pattern, locale=self.locale)

    def decimal(self, value: Decimal) -> str:
        return numbers.format_decimal(value, format="#,##0.######", locale=self.locale)

    def date(self, value: date) -> str:
        return dates.format_date(value, format="long", locale=self.locale)

    def timestamp(self, value: datetime) -> str:
        return dates.format_datetime(value, format="long", locale=self.locale)
