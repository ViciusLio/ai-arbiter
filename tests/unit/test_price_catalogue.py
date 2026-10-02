from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ai_arbiter.core.config import FinOpsSettings, PriceSettings, ReportingCurrencySettings
from ai_arbiter.core.errors import ConfigurationError
from ai_arbiter.core.ports.llm import Usage
from ai_arbiter.gateway.finops.catalogue import (
    ModelPrice,
    load_catalogue,
    packaged_catalogue_versions,
)


def price(**values: str | None) -> PriceSettings:
    defaults: dict[str, str | None] = {
        "provider": "acme",
        "model": "m",
        "input_per_million": "1.00",
        "output_per_million": "2.00",
    }
    return PriceSettings.model_validate({**defaults, **values})


def test_the_shipped_catalogue_prices_only_the_mock_provider() -> None:
    catalogue = load_catalogue()

    assert catalogue.version == packaged_catalogue_versions()[-1]
    assert catalogue.currency == "USD"
    assert {provider for provider, _, _ in catalogue.entries()} == {"mock"}
    assert catalogue.price("mock", "mock-small") == ModelPrice(
        input=Decimal("0.15"), output=Decimal("0.60"), cached_input=Decimal("0.075")
    )


def test_a_model_without_a_price_is_not_an_error() -> None:
    assert load_catalogue().price("openai_compat", "some-model") is None


def test_cost_is_exact_decimal_arithmetic_per_million_tokens() -> None:
    model = ModelPrice(input=Decimal("0.15"), output=Decimal("0.60"))

    assert model.cost(Usage(input_tokens=1_000_000, output_tokens=0)) == Decimal("0.15")
    assert model.cost(Usage(input_tokens=1, output_tokens=1)) == Decimal("0.000000750")
    assert model.cost(Usage(input_tokens=1234, output_tokens=567)) == Decimal("0.000525300")
    assert model.cost(Usage(input_tokens=0, output_tokens=0)) == Decimal(0)


def test_cached_input_tokens_are_priced_at_the_cached_rate() -> None:
    model = ModelPrice(input=Decimal("1.00"), output=Decimal("2.00"), cached_input=Decimal("0.10"))

    cost = model.cost(Usage(input_tokens=1000, output_tokens=0, cached_input_tokens=400))

    assert cost == Decimal("0.000640000")


def test_without_a_cached_price_cached_tokens_cost_the_full_input_price() -> None:
    model = ModelPrice(input=Decimal("1.00"), output=Decimal("2.00"))

    cost = model.cost(Usage(input_tokens=1000, output_tokens=0, cached_input_tokens=400))

    assert cost == Decimal("0.001")


def test_unknown_token_counts_have_no_cost() -> None:
    model = ModelPrice(input=Decimal("1.00"), output=Decimal("2.00"))

    assert model.cost(Usage()) is None
    assert model.cost(Usage(input_tokens=10)) is None


def test_a_regional_price_wins_over_the_general_one() -> None:
    catalogue = load_catalogue(
        FinOpsSettings(
            prices=(
                price(),
                price(region="westeurope", input_per_million="1.10"),
            )
        )
    )

    assert catalogue.price("acme", "m", "westeurope") == ModelPrice(
        Decimal("1.10"), Decimal("2.00")
    )
    assert catalogue.price("acme", "m", "eastus") == ModelPrice(Decimal("1.00"), Decimal("2.00"))
    assert catalogue.price("acme", "m") == ModelPrice(Decimal("1.00"), Decimal("2.00"))


def test_overrides_replace_shipped_prices_and_change_the_version() -> None:
    plain = load_catalogue()
    overridden = load_catalogue(
        FinOpsSettings(prices=(price(provider="mock", model="mock-small", input_per_million="9"),))
    )
    other = load_catalogue(
        FinOpsSettings(prices=(price(provider="mock", model="mock-small", input_per_million="8"),))
    )

    assert overridden.price("mock", "mock-small") == ModelPrice(Decimal(9), Decimal("2.00"))
    assert overridden.version.startswith(plain.version + "+")
    assert len({plain.version, overridden.version, other.version}) == 3
    assert load_catalogue(FinOpsSettings(prices=overridden_prices())).version == overridden.version


def overridden_prices() -> tuple[PriceSettings, ...]:
    return (price(provider="mock", model="mock-small", input_per_million="9"),)


@pytest.mark.parametrize("value", ["abc", "-1", "NaN", "Infinity", ""])
def test_a_price_must_be_a_non_negative_decimal(value: str) -> None:
    with pytest.raises(ValueError, match=r"decimal|zero or more"):
        price(input_per_million=value)


def test_a_price_written_as_a_number_is_refused() -> None:
    with pytest.raises(ValueError, match="string"):
        PriceSettings.model_validate(
            {"provider": "a", "model": "m", "input_per_million": 0.15, "output_per_million": "1"}
        )


def test_a_conversion_rate_must_be_positive() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        ReportingCurrencySettings(currency="EUR", rate="0", rate_as_of=date(2026, 10, 1))
    with pytest.raises(ValueError, match="pattern"):
        ReportingCurrencySettings(currency="euro", rate="0.9", rate_as_of=date(2026, 10, 1))


def test_a_catalogue_can_be_loaded_from_a_file(tmp_path: Path) -> None:
    path = tmp_path / "prices.yaml"
    path.write_text(
        "catalogue: mine\nversion: '7'\ncurrency: EUR\nas_of: 2026-09-01\n"
        "prices:\n  - { provider: p, model: m, input_per_million: '3', output_per_million: '4' }\n",
        encoding="utf-8",
    )

    catalogue = load_catalogue(FinOpsSettings(catalogue_file=path))

    assert (catalogue.version, catalogue.currency, catalogue.as_of) == (
        "7",
        "EUR",
        date(2026, 9, 1),
    )
    assert len(catalogue) == 1


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("catalogue: [", "not valid YAML"),
        ("catalogue: x\nversion: '1'\ncurrency: usd\nas_of: 2026-01-01", "currency"),
        (
            "catalogue: x\nversion: '1'\ncurrency: USD\nas_of: 2026-01-01\n"
            "prices: [{ provider: p, model: m, input_per_million: 0.5, output_per_million: '1' }]",
            "input_per_million",
        ),
    ],
)
def test_an_invalid_catalogue_file_is_a_configuration_error(
    tmp_path: Path, content: str, message: str
) -> None:
    path = tmp_path / "prices.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ConfigurationError, match=message):
        load_catalogue(FinOpsSettings(catalogue_file=path))


def test_a_missing_catalogue_file_is_a_configuration_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="not found"):
        load_catalogue(FinOpsSettings(catalogue_file=tmp_path / "absent.yaml"))
