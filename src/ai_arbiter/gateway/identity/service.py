"""Identity operations. Every query is filtered by tenant."""

import hmac
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.config.settings import PepperSettings
from ai_arbiter.core.domain.tenancy import AccessRole, TenantContext
from ai_arbiter.core.domain.time import SystemClock
from ai_arbiter.core.errors import (
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
)
from ai_arbiter.core.ports import Clock, SecretStore
from ai_arbiter.gateway.identity.keys import generate_key, hash_key, parse_key
from ai_arbiter.gateway.identity.model import (
    ApiKey,
    Principal,
    PrincipalKind,
    Project,
    RoleBinding,
    ScopeType,
    Team,
)

logger = logging.getLogger(__name__)

MIN_PEPPER_LENGTH = 32
ROLE_SCOPES = frozenset({ScopeType.TENANT, ScopeType.TEAM, ScopeType.PROJECT})

# Compared against when the key id is unknown, so that an unknown id and a wrong secret
# take the same time.
_ABSENT_HASH = "0" * 64


class PepperRing:
    """Resolves the configured peppers through the secret store, once each."""

    def __init__(self, settings: PepperSettings, secrets: SecretStore) -> None:
        self._settings = settings
        self._secrets = secrets
        self._resolved: dict[str, SecretStr] = {}

    @property
    def active_id(self) -> str:
        return self._settings.active

    def knows(self, pepper_id: str) -> bool:
        return pepper_id in self._settings.secrets

    async def get(self, pepper_id: str) -> SecretStr:
        """Raises ``ConfigurationError`` for an unknown id or a pepper that is too short."""
        cached = self._resolved.get(pepper_id)
        if cached is not None:
            return cached
        reference = self._settings.secrets.get(pepper_id)
        if reference is None:
            raise ConfigurationError(f"API key pepper '{pepper_id}' is not configured")
        pepper = await self._secrets.get(SecretRef.parse(reference))
        if len(pepper.get_secret_value()) < MIN_PEPPER_LENGTH:
            raise ConfigurationError(
                f"API key pepper '{pepper_id}' is shorter than {MIN_PEPPER_LENGTH} characters"
            )
        self._resolved[pepper_id] = pepper
        return pepper


@dataclass(frozen=True)
class AuthenticatedKey:
    context: TenantContext
    api_key_id: UUID
    key_id: str


class IdentityService:
    def __init__(self, peppers: PepperRing, clock: Clock | None = None) -> None:
        self._peppers = peppers
        self._clock = clock if clock is not None else SystemClock()

    # Teams and projects

    async def create_team(self, session: AsyncSession, tenant_id: UUID, name: str) -> Team:
        existing = await session.scalar(
            select(Team).where(Team.tenant_id == tenant_id, Team.name == name)
        )
        if existing is not None:
            raise ConflictError(f"team '{name}' already exists")
        team = Team(tenant_id=tenant_id, name=name)
        session.add(team)
        await session.flush()
        return team

    async def list_teams(self, session: AsyncSession, tenant_id: UUID) -> Sequence[Team]:
        return (
            await session.scalars(
                select(Team).where(Team.tenant_id == tenant_id).order_by(Team.name)
            )
        ).all()

    async def get_team(self, session: AsyncSession, tenant_id: UUID, team_id: UUID) -> Team:
        team = await session.scalar(
            select(Team).where(Team.tenant_id == tenant_id, Team.id == team_id)
        )
        if team is None:
            raise NotFoundError(f"team {team_id} not found")
        return team

    async def create_project(
        self, session: AsyncSession, tenant_id: UUID, team_id: UUID, name: str
    ) -> Project:
        await self.get_team(session, tenant_id, team_id)
        existing = await session.scalar(
            select(Project).where(
                Project.tenant_id == tenant_id, Project.team_id == team_id, Project.name == name
            )
        )
        if existing is not None:
            raise ConflictError(f"project '{name}' already exists in this team")
        project = Project(tenant_id=tenant_id, team_id=team_id, name=name)
        session.add(project)
        await session.flush()
        return project

    async def list_projects(self, session: AsyncSession, tenant_id: UUID) -> Sequence[Project]:
        return (
            await session.scalars(
                select(Project).where(Project.tenant_id == tenant_id).order_by(Project.name)
            )
        ).all()

    async def get_project(
        self, session: AsyncSession, tenant_id: UUID, project_id: UUID
    ) -> Project:
        project = await session.scalar(
            select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id)
        )
        if project is None:
            raise NotFoundError(f"project {project_id} not found")
        return project

    # Principals and roles

    async def create_principal(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        kind: PrincipalKind,
        display_name: str,
        external_id: str | None = None,
    ) -> Principal:
        principal = Principal(
            tenant_id=tenant_id, kind=kind.value, display_name=display_name, external_id=external_id
        )
        session.add(principal)
        await session.flush()
        return principal

    async def list_principals(self, session: AsyncSession, tenant_id: UUID) -> Sequence[Principal]:
        return (
            await session.scalars(
                select(Principal)
                .where(Principal.tenant_id == tenant_id)
                .order_by(Principal.created_at, Principal.id)
            )
        ).all()

    async def get_principal(
        self, session: AsyncSession, tenant_id: UUID, principal_id: UUID
    ) -> Principal:
        principal = await session.scalar(
            select(Principal).where(Principal.tenant_id == tenant_id, Principal.id == principal_id)
        )
        if principal is None:
            raise NotFoundError(f"principal {principal_id} not found")
        return principal

    async def grant_role(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        principal_id: UUID,
        role: AccessRole,
        scope_type: ScopeType = ScopeType.TENANT,
        scope_id: UUID | None = None,
    ) -> RoleBinding:
        """Give a principal a role on the tenant, a team or a project. Idempotent."""
        await self.get_principal(session, tenant_id, principal_id)
        if scope_type not in ROLE_SCOPES:
            raise ConflictError(f"a role cannot be scoped to '{scope_type.value}'")
        if scope_type is ScopeType.TENANT:
            target = tenant_id
        elif scope_id is None:
            raise ConflictError(f"a role scoped to a {scope_type.value} needs its id")
        elif scope_type is ScopeType.TEAM:
            target = (await self.get_team(session, tenant_id, scope_id)).id
        else:
            target = (await self.get_project(session, tenant_id, scope_id)).id

        existing = await session.scalar(
            select(RoleBinding).where(
                RoleBinding.principal_id == principal_id,
                RoleBinding.role == role.value,
                RoleBinding.scope_type == scope_type.value,
                RoleBinding.scope_id == target,
            )
        )
        if existing is not None:
            return existing
        binding = RoleBinding(
            tenant_id=tenant_id,
            principal_id=principal_id,
            role=role.value,
            scope_type=scope_type.value,
            scope_id=target,
        )
        session.add(binding)
        await session.flush()
        return binding

    async def roles_in_project(
        self, session: AsyncSession, principal_id: UUID, project: Project
    ) -> frozenset[AccessRole]:
        """Roles that hold in a project: bound to it, to its team or to the tenant."""
        roles = await session.scalars(
            select(RoleBinding.role).where(
                RoleBinding.tenant_id == project.tenant_id,
                RoleBinding.principal_id == principal_id,
                or_(
                    RoleBinding.scope_type == ScopeType.TENANT.value,
                    (RoleBinding.scope_type == ScopeType.TEAM.value)
                    & (RoleBinding.scope_id == project.team_id),
                    (RoleBinding.scope_type == ScopeType.PROJECT.value)
                    & (RoleBinding.scope_id == project.id),
                ),
            )
        )
        return frozenset(AccessRole(role) for role in roles)

    # API keys

    async def issue_api_key(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        project_id: UUID,
        principal_id: UUID,
        name: str,
        ai_system_id: UUID | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[ApiKey, str]:
        """Create a key. The second element is the key itself, available only here."""
        await self.get_project(session, tenant_id, project_id)
        await self.get_principal(session, tenant_id, principal_id)
        pepper_id = self._peppers.active_id
        pepper = await self._peppers.get(pepper_id)
        issued = generate_key()
        row = ApiKey(
            tenant_id=tenant_id,
            project_id=project_id,
            principal_id=principal_id,
            ai_system_id=ai_system_id,
            name=name,
            key_id=issued.key_id,
            key_hash=hash_key(pepper, issued.plaintext),
            pepper_id=pepper_id,
            created_at=self._clock.now(),
            expires_at=expires_at,
        )
        session.add(row)
        await session.flush()
        return row, issued.plaintext

    async def list_api_keys(self, session: AsyncSession, tenant_id: UUID) -> Sequence[ApiKey]:
        return (
            await session.scalars(
                select(ApiKey)
                .where(ApiKey.tenant_id == tenant_id)
                .order_by(ApiKey.created_at, ApiKey.id)
            )
        ).all()

    async def revoke_api_key(self, session: AsyncSession, tenant_id: UUID, key_id: str) -> ApiKey:
        """Revoke by public key id. Revoking twice keeps the first revocation time."""
        row = await session.scalar(
            select(ApiKey).where(ApiKey.tenant_id == tenant_id, ApiKey.key_id == key_id)
        )
        if row is None:
            raise NotFoundError(f"API key '{key_id}' not found")
        if row.revoked_at is None:
            row.revoked_at = self._clock.now()
            await session.flush()
        return row

    async def authenticate(self, session: AsyncSession, presented: str) -> AuthenticatedKey:
        """Identify the caller from an API key.

        Raises ``AuthenticationError`` with the same message whatever the reason, so that
        a response never tells a caller which part of a key was wrong.
        """
        key_id = parse_key(presented)
        if key_id is None:
            raise AuthenticationError("invalid API key")
        row = await session.scalar(select(ApiKey).where(ApiKey.key_id == key_id))

        if row is None or not self._peppers.knows(row.pepper_id):
            if row is not None:
                logger.error(
                    "API key refers to a pepper that is not configured",
                    extra={"key_id": key_id, "pepper_id": row.pepper_id},
                )
            pepper = await self._peppers.get(self._peppers.active_id)
            hmac.compare_digest(hash_key(pepper, presented), _ABSENT_HASH)
            raise AuthenticationError("invalid API key")

        pepper = await self._peppers.get(row.pepper_id)
        if not hmac.compare_digest(hash_key(pepper, presented), row.key_hash):
            raise AuthenticationError("invalid API key")
        now = self._clock.now()
        if row.revoked_at is not None or (row.expires_at is not None and row.expires_at <= now):
            raise AuthenticationError("invalid API key")

        project = await session.get(Project, row.project_id)
        if project is None:  # the foreign key makes this unreachable in a sound database
            raise AuthenticationError("invalid API key")
        roles = await self.roles_in_project(session, row.principal_id, project)
        return AuthenticatedKey(
            context=TenantContext(
                tenant_id=row.tenant_id,
                principal_id=row.principal_id,
                team_id=project.team_id,
                project_id=project.id,
                ai_system_id=row.ai_system_id,
                roles=roles,
            ),
            api_key_id=row.id,
            key_id=row.key_id,
        )
