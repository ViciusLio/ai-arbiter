"""Systems nobody declared, as the traffic shows them (ADR-0042).

A candidate is traffic that is attributed to no declared system, grouped by what makes
it: the project of the API key for Arbiter's own gateway, the group an external source
names for imported records. A candidate is a proposal. Nothing is declared from it.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from ai_arbiter.compliance.inventory.model import AISystem
from ai_arbiter.core.interaction import PII_CATEGORIES_AS_TEXT, Interaction, read_categories


@dataclass
class DiscoveredSystem:
    # "project" for traffic of Arbiter's gateway, "source" for imported records.
    kind: str
    project_id: UUID | None
    source: str | None
    group: str | None
    requests: int
    first_seen: datetime
    last_seen: datetime
    models: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)
    # Provider and model as they appear together; the provider can be unknown.
    uses: list[tuple[str, str]] = field(default_factory=list)
    pii_categories: list[str] = field(default_factory=list)

    @property
    def reference(self) -> str:
        """What identifies the candidate from one scan to the next."""
        if self.project_id is not None:
            return f"project:{self.project_id}"
        return f"source:{self.source}:{self.group}"

    @property
    def suggested_key(self) -> str:
        if self.project_id is not None:
            return f"discovered-{self.project_id.hex[-8:]}"
        slug = re.sub(r"[^a-z0-9]+", "-", f"{self.source}-{self.group}".lower()).strip("-")
        return f"discovered-{slug}"[:100].rstrip("-")

    def details(self) -> dict[str, Any]:
        """What a finding keeps as evidence: identifiers and counts."""
        return {
            "candidate": self.reference,
            "requests": self.requests,
            "models": self.models,
            "providers": self.providers,
            "pii_categories": self.pii_categories,
        }


def _undeclared(tenant_id: UUID, since: datetime) -> tuple[ColumnElement[bool], ...]:
    """Interactions tied to no system, by their key or by the project a system names."""
    declared_projects = select(AISystem.project_id).where(
        AISystem.tenant_id == tenant_id, AISystem.project_id.is_not(None)
    )
    return (
        Interaction.tenant_id == tenant_id,
        Interaction.ai_system_id.is_(None),
        Interaction.started_at >= since,
        or_(Interaction.project_id.is_(None), Interaction.project_id.not_in(declared_projects)),
    )


_GROUPED = or_(Interaction.project_id.is_not(None), Interaction.source_group.is_not(None))


async def discover(
    session: AsyncSession, tenant_id: UUID, since: datetime
) -> Sequence[DiscoveredSystem]:
    """Candidates in the traffic since ``since``, the busiest first."""
    undeclared = _undeclared(tenant_id, since)
    # Imported records have no project; records of the gateway have no group.
    source = func.coalesce(Interaction.source, "")
    group = func.coalesce(Interaction.source_group, "")
    candidates: dict[tuple[UUID | None, str, str], DiscoveredSystem] = {}

    def key_of(project_id: UUID | None, source_name: str, group_name: str) -> Any:
        return (project_id, "", "") if project_id is not None else (None, source_name, group_name)

    totals = await session.execute(
        select(
            Interaction.project_id,
            source,
            group,
            func.count(),
            func.min(Interaction.started_at),
            func.max(Interaction.started_at),
        )
        .where(*undeclared, _GROUPED)
        .group_by(Interaction.project_id, source, group)
    )
    for project_id, source_name, group_name, count, first, last in totals:
        key = key_of(project_id, source_name, group_name)
        found = candidates.get(key)
        if found is None:
            candidates[key] = DiscoveredSystem(
                kind="project" if project_id is not None else "source",
                project_id=project_id,
                source=None if project_id is not None else source_name,
                group=None if project_id is not None else group_name,
                requests=int(count),
                first_seen=first,
                last_seen=last,
            )
        else:
            # One project seen through several sources is still one candidate.
            found.requests += int(count)
            found.first_seen = min(found.first_seen, first)
            found.last_seen = max(found.last_seen, last)

    used = await session.execute(
        select(
            Interaction.project_id,
            source,
            group,
            Interaction.model,
            Interaction.requested_model,
            Interaction.provider,
        )
        .where(*undeclared, _GROUPED)
        .distinct()
    )
    for project_id, source_name, group_name, model, requested, provider in used:
        candidate = candidates[key_of(project_id, source_name, group_name)]
        name = model or requested
        if name and name not in candidate.models:
            candidate.models.append(str(name))
        if provider and provider not in candidate.providers:
            candidate.providers.append(str(provider))
        use = (str(provider or "unknown"), str(name)) if name else None
        if use is not None and use not in candidate.uses:
            candidate.uses.append(use)

    detected = await session.execute(
        select(Interaction.project_id, source, group, PII_CATEGORIES_AS_TEXT)
        .where(*undeclared, _GROUPED)
        .distinct()
    )
    for project_id, source_name, group_name, categories in detected:
        candidate = candidates[key_of(project_id, source_name, group_name)]
        for category in read_categories(categories):
            if category not in candidate.pii_categories:
                candidate.pii_categories.append(category)

    for candidate in candidates.values():
        candidate.models.sort()
        candidate.providers.sort()
        candidate.uses.sort()
        candidate.pii_categories.sort()
    return sorted(candidates.values(), key=lambda item: (-item.requests, item.reference))


async def ungrouped_requests(session: AsyncSession, tenant_id: UUID, since: datetime) -> int:
    """Requests tied to no system that nothing groups: no project and no source group."""
    return int(
        await session.scalar(
            select(func.count()).where(
                *_undeclared(tenant_id, since),
                and_(Interaction.project_id.is_(None), Interaction.source_group.is_(None)),
            )
        )
        or 0
    )


def draft_declaration(candidate: DiscoveredSystem, name: str | None = None) -> dict[str, Any]:
    """A declaration for a person to complete. It answers no question of the rule packs."""
    draft: dict[str, Any] = {
        "key": candidate.suggested_key,
        "name": name or candidate.group or candidate.suggested_key,
        "purpose": "",
        "lifecycle": "production",
        "roles": [],
        "models": [{"provider": provider, "model": model} for provider, model in candidate.uses],
        "facts": {},
    }
    if candidate.project_id is not None:
        draft["project_id"] = str(candidate.project_id)
    return draft
