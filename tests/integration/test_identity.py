from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from ai_arbiter.adapters.local.secrets import EnvSecretStore
from ai_arbiter.core.config import PepperSettings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.errors import (
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
)
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.gateway.identity.keys import generate_key
from ai_arbiter.gateway.identity.model import ApiKey, PrincipalKind, ScopeType
from ai_arbiter.gateway.identity.service import IdentityService, PepperRing
from tests.conftest import TEST_PEPPER, TEST_SECRETS


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.current = now

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def identity(secret_store: EnvSecretStore) -> IdentityService:
    return IdentityService(PepperRing(PepperSettings(), secret_store))


async def issue(
    identity: IdentityService,
    database: Database,
    tenant_id: UUID,
    *,
    role: AccessRole | None = AccessRole.DEVELOPER,
    expires_at: datetime | None = None,
) -> tuple[ApiKey, str]:
    async with database.transaction() as session:
        team = await identity.create_team(session, tenant_id, f"team-{new_id()}")
        project = await identity.create_project(session, tenant_id, team.id, "assistant")
        principal = await identity.create_principal(
            session, tenant_id, kind=PrincipalKind.SERVICE, display_name="assistant backend"
        )
        if role is not None:
            await identity.grant_role(session, tenant_id, principal_id=principal.id, role=role)
        return await identity.issue_api_key(
            session,
            tenant_id,
            project_id=project.id,
            principal_id=principal.id,
            name="ci",
            expires_at=expires_at,
        )


async def test_an_issued_key_authenticates_and_carries_its_context(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    row, key = await issue(identity, database, tenant_id)

    async with database.session() as session:
        authenticated = await identity.authenticate(session, key)

    assert authenticated.key_id == row.key_id
    assert authenticated.context.tenant_id == tenant_id
    assert authenticated.context.project_id == row.project_id
    assert authenticated.context.principal_id == row.principal_id
    assert authenticated.context.team_id is not None
    assert authenticated.context.roles == {AccessRole.DEVELOPER}


async def test_the_key_itself_is_not_stored(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    row, key = await issue(identity, database, tenant_id)
    secret = key.removeprefix(f"arb_{row.key_id}_")

    async with database.session() as session:
        stored = (await session.scalars(select(ApiKey))).one()

    values = [str(getattr(stored, column.name)) for column in ApiKey.__table__.columns]
    assert not any(key in value or secret in value for value in values)
    assert len(stored.key_hash) == 64


@pytest.mark.parametrize("presented", ["", "not-a-key", "Bearer something"])
async def test_a_malformed_key_is_refused(
    presented: str, identity: IdentityService, database: Database
) -> None:
    async with database.session() as session:
        with pytest.raises(AuthenticationError, match="invalid API key"):
            await identity.authenticate(session, presented)


async def test_a_well_formed_key_that_was_never_issued_is_refused(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    await issue(identity, database, tenant_id)

    async with database.session() as session:
        with pytest.raises(AuthenticationError, match="invalid API key"):
            await identity.authenticate(session, generate_key().plaintext)


async def test_a_revoked_key_is_refused_at_once(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    row, key = await issue(identity, database, tenant_id)

    async with database.transaction() as session:
        first = (await identity.revoke_api_key(session, tenant_id, row.key_id)).revoked_at
    async with database.transaction() as session:
        second = (await identity.revoke_api_key(session, tenant_id, row.key_id)).revoked_at

    assert first is not None
    assert second == first
    async with database.session() as session:
        with pytest.raises(AuthenticationError):
            await identity.authenticate(session, key)


async def test_an_expired_key_is_refused(
    secret_store: EnvSecretStore, database: Database, tenant_id: UUID
) -> None:
    clock = FixedClock(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
    identity = IdentityService(PepperRing(PepperSettings(), secret_store), clock)
    _, key = await issue(
        identity, database, tenant_id, expires_at=clock.current + timedelta(hours=1)
    )

    async with database.session() as session:
        assert (await identity.authenticate(session, key)).context.tenant_id == tenant_id
    clock.current += timedelta(hours=1)
    async with database.session() as session:
        with pytest.raises(AuthenticationError):
            await identity.authenticate(session, key)


async def test_a_key_does_not_verify_under_a_different_pepper(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    _, key = await issue(identity, database, tenant_id)
    other = IdentityService(
        PepperRing(
            PepperSettings(),
            EnvSecretStore({"ARBITER_SECRET_API_KEY_PEPPER": "a-different-pepper-" + "z" * 32}),
        )
    )

    async with database.session() as session:
        with pytest.raises(AuthenticationError):
            await other.authenticate(session, key)


async def test_old_keys_keep_working_after_the_pepper_is_rotated(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    old_row, old_key = await issue(identity, database, tenant_id)
    rotated = IdentityService(
        PepperRing(
            PepperSettings(
                active="2",
                secrets={"1": "secret://api-key-pepper", "2": "secret://api-key-pepper-2"},
            ),
            EnvSecretStore(
                {**TEST_SECRETS, "ARBITER_SECRET_API_KEY_PEPPER_2": "second-" + "p" * 32}
            ),
        )
    )

    new_row, new_key = await issue(rotated, database, tenant_id)

    assert (old_row.pepper_id, new_row.pepper_id) == ("1", "2")
    async with database.session() as session:
        assert (await rotated.authenticate(session, old_key)).key_id == old_row.key_id
        assert (await rotated.authenticate(session, new_key)).key_id == new_row.key_id


async def test_a_key_whose_pepper_was_removed_is_refused(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    _, key = await issue(identity, database, tenant_id)
    without = IdentityService(
        PepperRing(
            PepperSettings(active="2", secrets={"2": "secret://api-key-pepper"}),
            EnvSecretStore(dict(TEST_SECRETS)),
        )
    )

    async with database.session() as session:
        with pytest.raises(AuthenticationError):
            await without.authenticate(session, key)


async def test_a_short_pepper_is_a_configuration_error(database: Database, tenant_id: UUID) -> None:
    weak = IdentityService(
        PepperRing(PepperSettings(), EnvSecretStore({"ARBITER_SECRET_API_KEY_PEPPER": "short"}))
    )

    with pytest.raises(ConfigurationError, match="shorter than 32"):
        await issue(weak, database, tenant_id)


def test_the_active_pepper_must_be_listed() -> None:
    with pytest.raises(ValueError, match="not listed"):
        PepperSettings(active="9")


def test_a_pepper_must_be_a_secret_reference_not_a_value() -> None:
    with pytest.raises(ValueError, match="not a secret reference"):
        PepperSettings(secrets={"1": TEST_PEPPER})


async def test_roles_hold_in_the_scope_they_were_granted_on(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    async with database.transaction() as session:
        team = await identity.create_team(session, tenant_id, "platform")
        other_team = await identity.create_team(session, tenant_id, "research")
        project = await identity.create_project(session, tenant_id, team.id, "assistant")
        sibling = await identity.create_project(session, tenant_id, team.id, "search")
        elsewhere = await identity.create_project(session, tenant_id, other_team.id, "lab")
        principal = await identity.create_principal(
            session, tenant_id, kind=PrincipalKind.USER, display_name="Ada"
        )
        await identity.grant_role(
            session,
            tenant_id,
            principal_id=principal.id,
            role=AccessRole.DEVELOPER,
            scope_type=ScopeType.PROJECT,
            scope_id=project.id,
        )
        await identity.grant_role(
            session,
            tenant_id,
            principal_id=principal.id,
            role=AccessRole.AUDITOR,
            scope_type=ScopeType.TEAM,
            scope_id=team.id,
        )

    async with database.session() as session:
        assert await identity.roles_in_project(session, principal.id, project) == {
            AccessRole.DEVELOPER,
            AccessRole.AUDITOR,
        }
        assert await identity.roles_in_project(session, principal.id, sibling) == {
            AccessRole.AUDITOR
        }
        assert await identity.roles_in_project(session, principal.id, elsewhere) == frozenset()


async def test_granting_the_same_role_twice_creates_one_binding(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    async with database.transaction() as session:
        principal = await identity.create_principal(
            session, tenant_id, kind=PrincipalKind.USER, display_name="Ada"
        )
        first = await identity.grant_role(
            session, tenant_id, principal_id=principal.id, role=AccessRole.ADMIN
        )
        second = await identity.grant_role(
            session, tenant_id, principal_id=principal.id, role=AccessRole.ADMIN
        )

    assert first.id == second.id


async def test_a_role_cannot_be_scoped_to_something_that_is_not_a_tenant_team_or_project(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    async with database.transaction() as session:
        principal = await identity.create_principal(
            session, tenant_id, kind=PrincipalKind.USER, display_name="Ada"
        )
        with pytest.raises(ConflictError, match="cannot be scoped"):
            await identity.grant_role(
                session,
                tenant_id,
                principal_id=principal.id,
                role=AccessRole.ADMIN,
                scope_type=ScopeType.AI_SYSTEM,
                scope_id=new_id(),
            )
        with pytest.raises(ConflictError, match="needs its id"):
            await identity.grant_role(
                session,
                tenant_id,
                principal_id=principal.id,
                role=AccessRole.ADMIN,
                scope_type=ScopeType.TEAM,
            )


async def test_names_are_unique_within_their_parent(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    async with database.transaction() as session:
        team = await identity.create_team(session, tenant_id, "platform")
        await identity.create_project(session, tenant_id, team.id, "assistant")

        with pytest.raises(ConflictError, match="team 'platform' already exists"):
            await identity.create_team(session, tenant_id, "platform")
        with pytest.raises(ConflictError, match="project 'assistant' already exists"):
            await identity.create_project(session, tenant_id, team.id, "assistant")


async def test_one_tenant_cannot_see_or_use_what_belongs_to_another(
    identity: IdentityService, database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    row, _ = await issue(identity, database, tenant_id)

    async with database.transaction() as session:
        assert await identity.list_teams(session, other_tenant_id) == []
        assert await identity.list_projects(session, other_tenant_id) == []
        assert await identity.list_principals(session, other_tenant_id) == []
        assert await identity.list_api_keys(session, other_tenant_id) == []
        with pytest.raises(NotFoundError):
            await identity.get_project(session, other_tenant_id, row.project_id)
        with pytest.raises(NotFoundError):
            await identity.revoke_api_key(session, other_tenant_id, row.key_id)
        with pytest.raises(NotFoundError):
            await identity.issue_api_key(
                session,
                other_tenant_id,
                project_id=row.project_id,
                principal_id=row.principal_id,
                name="stolen",
            )
        with pytest.raises(NotFoundError):
            await identity.grant_role(
                session, other_tenant_id, principal_id=row.principal_id, role=AccessRole.ADMIN
            )


async def test_lists_return_what_was_created(
    identity: IdentityService, database: Database, tenant_id: UUID
) -> None:
    row, _ = await issue(identity, database, tenant_id)

    async with database.session() as session:
        assert [key.key_id for key in await identity.list_api_keys(session, tenant_id)] == [
            row.key_id
        ]
        assert len(await identity.list_teams(session, tenant_id)) == 1
        assert [p.name for p in await identity.list_projects(session, tenant_id)] == ["assistant"]
        assert len(await identity.list_principals(session, tenant_id)) == 1
