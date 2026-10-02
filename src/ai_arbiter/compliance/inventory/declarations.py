"""System declarations as written by people, in YAML or JSON."""

from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, ValidationError

from ai_arbiter.compliance.inventory.model import Lifecycle
from ai_arbiter.core.domain.risk import ActorRole
from ai_arbiter.core.errors import ArbiterError

FactAnswer = StrictBool | StrictInt | StrictStr | list[StrictStr] | None


class DeclarationError(ArbiterError):
    """A declaration file is missing or not valid."""


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleDeclaration(_Model):
    role: ActorRole
    basis: str = Field(default="", max_length=500)
    since: date | None = None


class ModelDeclaration(_Model):
    provider: str
    model: str
    # Whether the model is a general-purpose AI model within the meaning of the AI Act.
    general_purpose: bool | None = None


class SystemDeclaration(_Model):
    key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$")
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="", max_length=2000)
    lifecycle: Lifecycle = Lifecycle.PRODUCTION
    owner_principal_id: UUID | None = None
    project_id: UUID | None = None
    roles: list[RoleDeclaration] = Field(default_factory=list)
    models: list[ModelDeclaration] = Field(default_factory=list)
    # Named sets of answers from ``fact_sets`` of the same file, applied in order
    # before the system's own ``facts``.
    use: list[str] = Field(default_factory=list)
    # Answers to the questions of the rule packs. An omitted fact is "not answered",
    # which is different from false.
    facts: dict[str, FactAnswer] = Field(default_factory=dict)

    def answered(self) -> dict[str, Any]:
        return {name: value for name, value in self.facts.items() if value is not None}


class DeclarationFile(_Model):
    # Answers shared by several systems, for example "no prohibited practice".
    fact_sets: dict[str, dict[str, FactAnswer]] = Field(default_factory=dict)
    systems: list[SystemDeclaration] = Field(min_length=1)


def parse_declarations(text: str, *, origin: str = "declaration") -> list[SystemDeclaration]:
    try:
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DeclarationError(f"{origin}: not valid YAML") from exc
    try:
        parsed = DeclarationFile.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        )
        raise DeclarationError(f"{origin}: {problems}") from exc
    keys = [system.key for system in parsed.systems]
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    if duplicates:
        raise DeclarationError(f"{origin}: system keys used twice: {', '.join(duplicates)}")
    resolved: list[SystemDeclaration] = []
    for system in parsed.systems:
        facts: dict[str, Any] = {}
        for name in system.use:
            if name not in parsed.fact_sets:
                raise DeclarationError(
                    f"{origin}: system '{system.key}' uses unknown fact set '{name}'"
                )
            facts.update(parsed.fact_sets[name])
        facts.update(system.facts)
        resolved.append(system.model_copy(update={"facts": facts, "use": []}))
    return resolved


def load_declarations(path: Path) -> list[SystemDeclaration]:
    if not path.is_file():
        raise DeclarationError(f"declaration file not found: {path}")
    return parse_declarations(path.read_text(encoding="utf-8"), origin=str(path))
