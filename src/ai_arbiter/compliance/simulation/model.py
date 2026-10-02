"""A scenario as written in YAML. Data only: no code, like a rule pack (ADR-0043)."""

from importlib import resources
from typing import Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_arbiter.compliance.classifier.model import ReviewDecision
from ai_arbiter.compliance.inventory.declarations import SystemDeclaration, parse_declarations
from ai_arbiter.core.domain.risk import RiskTier
from ai_arbiter.core.errors import ArbiterError, NotFoundError

_DIRECTORY = "scenarios"
_SUFFIX = ".yaml"


class ScenarioError(ArbiterError):
    """A scenario file is not valid."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Localised(_Model):
    en: str = Field(min_length=1)
    it: str = Field(min_length=1)

    def text(self, locale: str) -> str:
        return self.it if locale == "it" else self.en


class TrafficSpec(_Model):
    """Requests to write, as counts. A scenario never holds prompt or completion text."""

    # The declared system the requests belong to, or the group that makes them when no
    # system is declared for them.
    system: str | None = None
    group: str | None = None
    requests: int = Field(ge=1, le=5000)
    model: str = Field(min_length=1, max_length=200)
    provider: str | None = Field(default=None, max_length=100)
    pii_categories: tuple[str, ...] = ()
    days_ago: int = Field(default=1, ge=0, le=29)

    @model_validator(mode="after")
    def _one_origin(self) -> Self:
        if (self.system is None) == (self.group is None):
            raise ValueError("name either the system or the group the requests come from")
        return self


class ReviewSpec(_Model):
    system: str
    decision: ReviewDecision = ReviewDecision.CONFIRMED
    tier: RiskTier | None = None
    reason: str = ""


class ExpectedSystem(_Model):
    tier: RiskTier
    # Rule ids of the findings that stay open after the scan. Empty: no findings.
    findings: tuple[str, ...] = ()


class Expected(_Model):
    systems: dict[str, ExpectedSystem]
    # Groups the scan is expected to name as candidate systems.
    candidates: tuple[str, ...] = ()


class Scenario(_Model):
    scenario: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,49}$")
    title: Localised
    description: Localised
    # A declaration file: ``fact_sets`` and ``systems``, as ``arbiter systems apply`` reads it.
    inventory: dict[str, Any]
    # Systems that are given an owner. The others are left without one.
    owned: tuple[str, ...] = ()
    reviews: tuple[ReviewSpec, ...] = ()
    traffic: tuple[TrafficSpec, ...] = ()
    expected: Expected

    def declarations(self) -> list[SystemDeclaration]:
        return parse_declarations(yaml.safe_dump(self.inventory), origin=self.scenario)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        declared = {declaration.key for declaration in self.declarations()}
        named = {
            "owned": set(self.owned),
            "reviews": {review.system for review in self.reviews},
            "traffic": {item.system for item in self.traffic if item.system is not None},
        }
        for where, keys in named.items():
            unknown = sorted(keys - declared)
            if unknown:
                raise ValueError(f"{where}: '{unknown[0]}' is not a system of the scenario")
        if set(self.expected.systems) != declared:
            raise ValueError(
                "expected.systems must name every system of the scenario, and no other"
            )
        return self


def parse_scenario(text: str, *, origin: str) -> Scenario:
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScenarioError(f"{origin}: not valid YAML") from exc
    try:
        return Scenario.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'scenario'}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise ScenarioError(f"{origin}: {problems}") from exc


def packaged_scenarios() -> list[str]:
    """Names of the scenarios shipped with the package, sorted."""
    directory = resources.files("ai_arbiter").joinpath(_DIRECTORY)
    return sorted(
        entry.name.removesuffix(_SUFFIX)
        for entry in directory.iterdir()
        if entry.name.endswith(_SUFFIX)
    )


def load_scenario(name: str) -> Scenario:
    if name not in packaged_scenarios():
        known = ", ".join(packaged_scenarios()) or "none"
        raise NotFoundError(f"no scenario named '{name}' (available: {known})")
    resource = resources.files("ai_arbiter").joinpath(_DIRECTORY, name + _SUFFIX)
    scenario = parse_scenario(resource.read_text(encoding="utf-8"), origin=name)
    if scenario.scenario != name:
        raise ScenarioError(f"{name}: the file declares the scenario '{scenario.scenario}'")
    return scenario
