"""Versioned price catalogue (ADR-0030)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_arbiter.core.canonical_json import sha256_hex
from ai_arbiter.core.config.settings import FinOpsSettings, PriceSettings, parse_decimal
from ai_arbiter.core.errors import ConfigurationError
from ai_arbiter.core.persistence.types import quantize_amount
from ai_arbiter.core.ports.llm import Usage

_PACKAGED = "ai_arbiter.rulepacks"
_DIRECTORY = "prices"
_FILE = "prices.yaml"
_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPrice:
    """Prices per million tokens, in the catalogue's currency."""

    input: Decimal
    output: Decimal
    cached_input: Decimal | None = None

    @classmethod
    def of(cls, price: PriceSettings) -> "ModelPrice":
        return cls(
            input=parse_decimal(price.input_per_million),
            output=parse_decimal(price.output_per_million),
            cached_input=(
                parse_decimal(price.cached_input_per_million)
                if price.cached_input_per_million is not None
                else None
            ),
        )

    def cost(self, usage: Usage) -> Decimal | None:
        """Cost of a usage, or ``None`` when the token counts are not known."""
        if usage.input_tokens is None or usage.output_tokens is None:
            return None
        cached = min(usage.cached_input_tokens or 0, usage.input_tokens)
        if self.cached_input is None:
            cached = 0
        total = (
            (usage.input_tokens - cached) * self.input
            + cached * (self.cached_input or Decimal(0))
            + usage.output_tokens * self.output
        )
        return quantize_amount(total / _MILLION)


class _CatalogueFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalogue: str
    version: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    as_of: date
    prices: tuple[PriceSettings, ...] = ()


def _key(provider: str, model: str, region: str | None) -> tuple[str, str, str | None]:
    return (provider, model, region)


class PriceCatalogue:
    def __init__(
        self,
        *,
        version: str,
        currency: str,
        as_of: date,
        prices: Sequence[PriceSettings],
        overrides: Sequence[PriceSettings] = (),
    ) -> None:
        self.currency = currency
        self.as_of = as_of
        self._prices: dict[tuple[str, str, str | None], ModelPrice] = {
            _key(price.provider, price.model, price.region): ModelPrice.of(price)
            for price in (*prices, *overrides)
        }
        # Two different sets of prices must never share a version.
        self.version = version
        if overrides:
            digest = sha256_hex(
                sorted(
                    [
                        price.provider,
                        price.model,
                        price.region or "",
                        price.input_per_million,
                        price.output_per_million,
                        price.cached_input_per_million or "",
                    ]
                    for price in overrides
                )
            )
            self.version = f"{version}+{digest[:8]}"

    def __len__(self) -> int:
        return len(self._prices)

    def price(self, provider: str, model: str, region: str | None = None) -> ModelPrice | None:
        """The price for a region if there is one, else the price without a region."""
        specific = self._prices.get(_key(provider, model, region)) if region else None
        return specific or self._prices.get(_key(provider, model, None))

    def entries(self) -> Mapping[tuple[str, str, str | None], ModelPrice]:
        return dict(self._prices)


def _parse(text: str, origin: str) -> _CatalogueFile:
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"price catalogue {origin}: not valid YAML") from exc
    try:
        return _CatalogueFile.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError(f"price catalogue {origin}: {problems}") from exc


def packaged_catalogue_versions() -> list[str]:
    directory = resources.files(_PACKAGED).joinpath(_DIRECTORY)
    return sorted(entry.name for entry in directory.iterdir() if entry.joinpath(_FILE).is_file())


def load_catalogue(settings: FinOpsSettings | None = None) -> PriceCatalogue:
    """The catalogue named in the settings, or the newest one shipped, plus overrides."""
    settings = settings if settings is not None else FinOpsSettings()
    if settings.catalogue_file is not None:
        path = Path(settings.catalogue_file)
        if not path.is_file():
            raise ConfigurationError(f"price catalogue not found: {path}")
        parsed = _parse(path.read_text(encoding="utf-8"), str(path))
    else:
        version = packaged_catalogue_versions()[-1]
        resource = resources.files(_PACKAGED).joinpath(_DIRECTORY, version, _FILE)
        parsed = _parse(resource.read_text(encoding="utf-8"), version)
    return PriceCatalogue(
        version=parsed.version,
        currency=parsed.currency,
        as_of=parsed.as_of,
        prices=parsed.prices,
        overrides=settings.prices,
    )
