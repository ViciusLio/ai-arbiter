"""Inventory operations. Every query is filtered by tenant."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.inventory.declarations import SystemDeclaration
from ai_arbiter.compliance.inventory.model import (
    AISystem,
    AISystemProject,
    AISystemRole,
    Origin,
    SystemChanged,
    SystemDeclared,
)
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.domain.risk import ActorRole
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.errors import ConflictError, NotFoundError
from ai_arbiter.core.ports import AuditLog, EventBus
from ai_arbiter.core.rules import FactType

Change = Literal["created", "changed", "unchanged"]


@dataclass(frozen=True)
class DeclaredSystem:
    system: AISystem
    roles: tuple[AISystemRole, ...]
    change: Change


def _type_matches(value: object, declared: FactType) -> bool:
    if declared is FactType.BOOLEAN:
        return isinstance(value, bool)
    if declared is FactType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if declared is FactType.STRING:
        return isinstance(value, str)
    return isinstance(value, list)


class InventoryService:
    def __init__(
        self,
        audit: AuditLog,
        bus: EventBus,
        known_facts: Mapping[str, FactType],
        clock: Clock | None = None,
    ) -> None:
        self._audit = audit
        self._bus = bus
        self._known_facts = known_facts
        self._clock = clock if clock is not None else SystemClock()

    def _check_facts(self, declaration: SystemDeclaration) -> None:
        """Refuse facts no rule pack asks for, and answers of the wrong type.

        A misspelt fact would otherwise sit in the declaration unused while the real one
        stays unanswered.
        """
        answers = declaration.answered()
        unknown = sorted(set(answers) - set(self._known_facts))
        if unknown:
            raise ConflictError(
                f"system '{declaration.key}': unknown facts: {', '.join(unknown)}. "
                "Run 'arbiter systems facts' for the list."
            )
        for name, value in answers.items():
            if not _type_matches(value, self._known_facts[name]):
                raise ConflictError(
                    f"system '{declaration.key}': fact '{name}' must be a "
                    f"{self._known_facts[name].value}"
                )

    async def declare(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        declaration: SystemDeclaration,
        *,
        actor_id: UUID | None = None,
    ) -> DeclaredSystem:
        """Create the system or bring it in line with the declaration. Idempotent."""
        self._check_facts(declaration)
        roles = {item.role.value: item for item in declaration.roles}
        if len(roles) != len(declaration.roles):
            raise ConflictError(f"system '{declaration.key}': a role is listed twice")
        values = {
            "name": declaration.name,
            "purpose": declaration.purpose,
            "lifecycle": declaration.lifecycle.value,
            "owner_principal_id": declaration.owner_principal_id,
            "attributes": declaration.answered(),
            "models_used": [model.model_dump(mode="json") for model in declaration.models],
        }
        system = await session.scalar(
            select(AISystem).where(AISystem.tenant_id == tenant_id, AISystem.key == declaration.key)
        )
        now = self._clock.now()
        change: Change
        if system is None:
            system = AISystem(
                tenant_id=tenant_id,
                key=declaration.key,
                origin=Origin.DECLARED.value,
                declared_at=now,
                updated_at=now,
                **values,
            )
            session.add(system)
            await session.flush()
            existing: dict[str, AISystemRole] = {}
            change = "created"
        else:
            existing = {role.role: role for role in await self.roles(session, system)}
            same_roles = {name: (role.basis, role.since) for name, role in existing.items()} == {
                name: (item.basis, item.since) for name, item in roles.items()
            }
            same_projects = await self.projects(session, system) == declaration.projects()
            same = (
                same_roles
                and same_projects
                and all(getattr(system, name) == value for name, value in values.items())
            )
            change = "unchanged" if same and system.origin == Origin.DECLARED.value else "changed"
            if change == "changed":
                for name, value in values.items():
                    setattr(system, name, value)
                system.origin = Origin.DECLARED.value
                system.updated_at = now

        if change != "unchanged":
            await session.execute(
                delete(AISystemRole).where(AISystemRole.ai_system_id == system.id)
            )
            for item in roles.values():
                session.add(
                    AISystemRole(
                        tenant_id=tenant_id,
                        ai_system_id=system.id,
                        role=item.role.value,
                        basis=item.basis,
                        since=item.since,
                    )
                )
            await session.execute(
                delete(AISystemProject).where(AISystemProject.ai_system_id == system.id)
            )
            for project_id in declaration.projects():
                session.add(
                    AISystemProject(
                        tenant_id=tenant_id, ai_system_id=system.id, project_id=project_id
                    )
                )
            await session.flush()
            await self._audit.append(
                session,
                tenant_id,
                AuditRecord(
                    action="system.declared" if change == "created" else "system.changed",
                    outcome="ok",
                    actor_id=actor_id,
                    resource_type="ai_system",
                    resource_id=str(system.id),
                ),
            )
            event = SystemDeclared if change == "created" else SystemChanged
            await self._bus.publish(
                event(tenant_id=tenant_id, ai_system_id=system.id), session=session
            )
        return DeclaredSystem(system, tuple(await self.roles(session, system)), change)

    async def roles(self, session: AsyncSession, system: AISystem) -> Sequence[AISystemRole]:
        return (
            await session.scalars(
                select(AISystemRole)
                .where(AISystemRole.ai_system_id == system.id)
                .order_by(AISystemRole.role)
            )
        ).all()

    async def projects(self, session: AsyncSession, system: AISystem) -> tuple[UUID, ...]:
        """The projects whose requests belong to the system, in a stable order."""
        found = await session.scalars(
            select(AISystemProject.project_id).where(AISystemProject.ai_system_id == system.id)
        )
        return tuple(sorted(found.all(), key=str))

    async def role_names(self, session: AsyncSession, system: AISystem) -> frozenset[ActorRole]:
        return frozenset(ActorRole(role.role) for role in await self.roles(session, system))

    async def list(self, session: AsyncSession, tenant_id: UUID) -> Sequence[AISystem]:
        return (
            await session.scalars(
                select(AISystem).where(AISystem.tenant_id == tenant_id).order_by(AISystem.key)
            )
        ).all()

    async def get(self, session: AsyncSession, tenant_id: UUID, key: str) -> AISystem:
        system = await session.scalar(
            select(AISystem).where(AISystem.tenant_id == tenant_id, AISystem.key == key)
        )
        if system is None:
            raise NotFoundError(f"AI system '{key}' not found")
        return system

    async def get_by_id(self, session: AsyncSession, tenant_id: UUID, system_id: UUID) -> AISystem:
        system = await session.scalar(
            select(AISystem).where(AISystem.tenant_id == tenant_id, AISystem.id == system_id)
        )
        if system is None:
            raise NotFoundError(f"AI system {system_id} not found")
        return system
