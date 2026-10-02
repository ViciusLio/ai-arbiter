"""Rule pack schema (ADR-0012).

A rule pack is data. A condition is a tree of ``all`` / ``any`` / ``not`` over comparisons
of named facts; the operators are a closed set and nothing in a pack is executed.
"""

import re
from datetime import date
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    Tag,
    model_validator,
)

Scalar = StrictBool | StrictInt | StrictStr

OPERATORS = ("eq", "ne", "in", "contains", "gt", "lt", "exists")
_FACT_NAME = re.compile(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*")
_RULE_ID = re.compile(r"[A-Z][A-Z0-9]*(-[A-Z0-9]+)*")


class FactType(StrEnum):
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    LIST = "list"  # a list of strings


class RuleKind(StrEnum):
    POLICY = "policy"
    CLASSIFICATION = "classification"
    FINDING = "finding"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)


class Comparison(_Model):
    """One fact compared with a value from the pack, with exactly one operator."""

    fact: str
    eq: Scalar | None = None
    ne: Scalar | None = None
    in_: tuple[Scalar, ...] | None = Field(default=None, alias="in")
    contains: StrictStr | None = None
    gt: StrictInt | None = None
    lt: StrictInt | None = None
    exists: StrictBool | None = None

    @model_validator(mode="after")
    def _one_operator(self) -> Self:
        if not _FACT_NAME.fullmatch(self.fact):
            raise ValueError(f"invalid fact name '{self.fact}'")
        given = self.model_fields_set - {"fact"}
        if len(given) != 1:
            raise ValueError(
                f"a comparison on '{self.fact}' needs exactly one of: {', '.join(OPERATORS)}"
            )
        if getattr(self, next(iter(given))) is None:
            raise ValueError(f"the operator on '{self.fact}' has no value")
        return self

    @property
    def operator(self) -> str:
        name = next(iter(self.model_fields_set - {"fact"}))
        return "in" if name == "in_" else name

    @property
    def expected(self) -> Any:
        return getattr(self, next(iter(self.model_fields_set - {"fact"})))


class AllOf(_Model):
    all: tuple["Condition", ...] = Field(min_length=1)


class AnyOf(_Model):
    any: tuple["Condition", ...] = Field(min_length=1)


class Not(_Model):
    not_: "Condition" = Field(alias="not")


def _condition_kind(value: Any) -> str:
    keys = value if isinstance(value, dict) else getattr(value, "model_fields_set", ())
    for key, tag in (("all", "all"), ("any", "any"), ("not", "not"), ("not_", "not")):
        if key in keys:
            return tag
    return "comparison"


Condition = Annotated[
    Annotated[AllOf, Tag("all")]
    | Annotated[AnyOf, Tag("any")]
    | Annotated[Not, Tag("not")]
    | Annotated[Comparison, Tag("comparison")],
    Discriminator(_condition_kind),
]

AllOf.model_rebuild()
AnyOf.model_rebuild()
Not.model_rebuild()


class LegalRef(_Model):
    regulation: str = "EU-AI-ACT"
    article: str


class Outcome(_Model):
    outcome: str = Field(min_length=1)
    legal_refs: tuple[LegalRef, ...] = ()
    applies_from: date | None = None
    message_key: str = Field(min_length=1)


class Rule(_Model):
    id: str
    kind: RuleKind
    description: str = ""
    roles: tuple[str, ...] = ()
    when: Condition
    then: Outcome

    @model_validator(mode="after")
    def _check_id(self) -> Self:
        if not _RULE_ID.fullmatch(self.id):
            raise ValueError(f"invalid rule id '{self.id}': use capitals, digits and hyphens")
        return self


class Regulation(_Model):
    """Legal basis of a pack that encodes a regulation."""

    id: str
    amended_by: tuple[str, ...] = ()
    as_of: date
    verified_against: Literal["primary", "secondary"]


def comparisons(condition: Any) -> list[Comparison]:
    """Every comparison in a condition tree, depth first."""
    if isinstance(condition, Comparison):
        return [condition]
    if isinstance(condition, Not):
        return comparisons(condition.not_)
    children = condition.all if isinstance(condition, AllOf) else condition.any
    return [leaf for child in children for leaf in comparisons(child)]


def _type_of(value: object) -> FactType:
    if isinstance(value, bool):
        return FactType.BOOLEAN
    if isinstance(value, int):
        return FactType.INTEGER
    return FactType.STRING


def _check_comparison(rule_id: str, comparison: Comparison, declared: FactType) -> None:
    operator, expected = comparison.operator, comparison.expected
    where = f"rule {rule_id}: '{comparison.fact}' is declared as {declared.value}"
    if operator == "exists":
        return
    if operator in ("gt", "lt"):
        if declared is not FactType.INTEGER:
            raise ValueError(f"{where}, and '{operator}' needs an integer fact")
        return
    if operator == "contains":
        if declared not in (FactType.LIST, FactType.STRING):
            raise ValueError(f"{where}, and 'contains' needs a list or a string fact")
        return
    if declared is FactType.LIST:
        raise ValueError(f"{where}; compare a list with 'contains' or 'exists'")
    values = expected if operator == "in" else (expected,)
    for value in values:
        if _type_of(value) is not declared:
            raise ValueError(f"{where}, but is compared with the {_type_of(value).value} {value!r}")


class RulePack(_Model):
    pack: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    version: str = Field(min_length=1)
    description: str = ""
    regulation: Regulation | None = None
    facts: dict[str, FactType]
    rules: tuple[Rule, ...]

    @model_validator(mode="after")
    def _check_rules(self) -> Self:
        for name in self.facts:
            if not _FACT_NAME.fullmatch(name):
                raise ValueError(f"invalid fact name '{name}'")
        seen: set[str] = set()
        for rule in self.rules:
            if rule.id in seen:
                raise ValueError(f"rule id {rule.id} is used twice")
            seen.add(rule.id)
            for comparison in comparisons(rule.when):
                declared = self.facts.get(comparison.fact)
                if declared is None:
                    raise ValueError(
                        f"rule {rule.id} uses the fact '{comparison.fact}', which the pack "
                        "does not declare"
                    )
                _check_comparison(rule.id, comparison, declared)
        return self
