"""The A2A registry: which agents exist, what their card says, and who may call them."""

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.agents import PROXIED_BINDINGS, AgentCardReader
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.config.settings import A2aSettings
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.errors import ConflictError, MissingExtraError, NotFoundError
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.ports import AuditLog
from ai_arbiter.gateway.a2a.model import NOT_FETCHED, A2aAgent, A2aGrant
from ai_arbiter.gateway.identity.model import ScopeType
from ai_arbiter.gateway.mcp.catalogue import Caller
from ai_arbiter.gateway.urls import checked_url, host_of

_KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,99}")
_GRANT_SCOPES = (ScopeType.TENANT, ScopeType.PROJECT, ScopeType.AI_SYSTEM)


class AgentGovernability:
    """Whether a proxy can stand in front of an agent, and why not."""

    GOVERNABLE = "governable"
    NOT_FETCHED = "not_fetched"  # its card was never read
    NO_PROXIED_BINDING = "no_proxied_binding"  # it offers gRPC only, or nothing usable
    DISABLED = "disabled"


def usable_interfaces(
    agent: A2aAgent, allow_http_hosts: Sequence[str] = ()
) -> list[dict[str, str]]:
    """The interfaces of an agent a proxy may forward to.

    An interface counts only if its binding is one the proxy speaks, its URL passes the
    same rule as the card's, and it is on the host the card was read from: a card must
    not be able to point requests, with the agent's credential, at another host.
    """
    card_host = host_of(agent.card_url)
    usable = []
    for item in agent.interfaces or []:
        if not isinstance(item, Mapping) or item.get("binding") not in PROXIED_BINDINGS:
            continue
        url = str(item.get("url") or "")
        try:
            checked_url(
                url,
                what="an interface",
                allow_http_hosts=allow_http_hosts,
                setting="a2a.allow_http_hosts",
            )
        except ConflictError:
            continue
        if host_of(url) != card_host:
            continue
        usable.append(
            {"binding": str(item["binding"]), "url": url, "version": str(item.get("version") or "")}
        )
    return usable


def governability(agent: A2aAgent, allow_http_hosts: Sequence[str] = ()) -> str:
    if not agent.enabled:
        return AgentGovernability.DISABLED
    if agent.verification == NOT_FETCHED:
        return AgentGovernability.NOT_FETCHED
    if not usable_interfaces(agent, allow_http_hosts):
        return AgentGovernability.NO_PROXIED_BINDING
    return AgentGovernability.GOVERNABLE


class A2aRegistry:
    def __init__(
        self,
        *,
        reader: AgentCardReader,
        settings: A2aSettings,
        clock: Clock | None = None,
        transport: Any = None,
    ) -> None:
        self._reader = reader
        self.settings = settings
        self._clock = clock if clock is not None else SystemClock()
        self._transport = transport
        self._client: Any = None

    def _http(self) -> Any:
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise MissingExtraError("gateway", "Reading an Agent Card") from exc
            # Redirects are never followed: the card is read from the address the
            # operator registered, or not at all.
            self._client = httpx.AsyncClient(transport=self._transport, follow_redirects=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def governability(self, agent: A2aAgent) -> str:
        return governability(agent, self.settings.allow_http_hosts)

    def usable_interfaces(self, agent: A2aAgent) -> list[dict[str, str]]:
        return usable_interfaces(agent, self.settings.allow_http_hosts)

    # Agents

    async def register(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        *,
        key: str,
        name: str,
        card_url: str,
        ai_system_id: UUID | None = None,
        credential: str | None = None,
    ) -> A2aAgent:
        if not _KEY.fullmatch(key):
            raise ConflictError(
                "the key of an agent uses lower-case letters, digits and hyphens, 100 at most"
            )
        if not name.strip():
            raise ConflictError("an agent needs a name")
        card_url = checked_url(
            card_url,
            what="an Agent Card",
            allow_http_hosts=self.settings.allow_http_hosts,
            setting="a2a.allow_http_hosts",
        )
        if credential is not None:
            try:
                SecretRef.parse(credential)
            except ValueError as error:
                raise ConflictError(f"credential: {error}") from error
        existing = await session.scalar(
            select(A2aAgent).where(A2aAgent.tenant_id == tenant_id, A2aAgent.key == key)
        )
        if existing is not None:
            raise ConflictError(f"an agent with the key '{key}' already exists")
        agent = A2aAgent(
            tenant_id=tenant_id,
            key=key,
            name=name.strip(),
            card_url=card_url,
            ai_system_id=ai_system_id,
            credential=credential,
            created_at=self._clock.now(),
        )
        session.add(agent)
        await session.flush()
        return agent

    async def list(self, session: AsyncSession, tenant_id: UUID) -> Sequence[A2aAgent]:
        return (
            await session.scalars(
                select(A2aAgent).where(A2aAgent.tenant_id == tenant_id).order_by(A2aAgent.key)
            )
        ).all()

    async def find(self, session: AsyncSession, tenant_id: UUID, key: str) -> A2aAgent | None:
        return await session.scalar(
            select(A2aAgent).where(A2aAgent.tenant_id == tenant_id, A2aAgent.key == key)
        )

    async def get(self, session: AsyncSession, tenant_id: UUID, key: str) -> A2aAgent:
        agent = await self.find(session, tenant_id, key)
        if agent is None:
            raise NotFoundError(f"no agent with the key '{key}'")
        return agent

    async def set_enabled(
        self, session: AsyncSession, tenant_id: UUID, key: str, enabled: bool
    ) -> A2aAgent:
        agent = await self.get(session, tenant_id, key)
        agent.enabled = enabled
        await session.flush()
        return agent

    async def remove(self, session: AsyncSession, tenant_id: UUID, key: str) -> A2aAgent:
        """Delete an agent with its grants. Past calls keep its key."""
        agent = await self.get(session, tenant_id, key)
        await session.execute(delete(A2aGrant).where(A2aGrant.agent_id == agent.id))
        await session.delete(agent)
        await session.flush()
        return agent

    # The card

    async def refresh(
        self,
        database: Database,
        audit: AuditLog,
        tenant_id: UUID,
        key: str,
        *,
        actor_id: UUID | None = None,
    ) -> A2aAgent:
        """Read the Agent Card again, verify it and store what it says.

        The request is made with no transaction open. Raises ``ConflictError`` when the
        card cannot be read or is not a card.
        """
        import httpx

        async with database.session() as session:
            agent = await self.get(session, tenant_id, key)
        try:
            response = await self._http().get(
                agent.card_url,
                headers={"accept": "application/json"},
                timeout=self.settings.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise ConflictError(
                f"the card of '{key}' could not be read ({type(exc).__name__})"
            ) from exc
        if response.status_code != 200:
            raise ConflictError(
                f"the card of '{key}' could not be read (HTTP {response.status_code})"
            )
        document = response.content
        if len(document) > self.settings.max_card_bytes:
            raise ConflictError(f"the card of '{key}' is larger than a2a.max_card_bytes")
        try:
            summary = self._reader.read(
                document,
                keys={trusted.kid: trusted.jwk for trusted in self.settings.trusted_keys},
                algorithms=self.settings.algorithms,
            )
        except ValueError as error:
            raise ConflictError(f"the card of '{key}': {error}") from error

        digest = hashlib.sha256(document).hexdigest()
        async with database.transaction() as session:
            stored = await self.get(session, tenant_id, key)
            changed = stored.card_sha256 is not None and stored.card_sha256 != digest
            stored.card_name = summary.name[:200]
            stored.card_version = summary.version[:50] or None
            stored.card_sha256 = digest
            stored.interfaces = [
                {"binding": item.binding, "url": item.url[:2000], "version": item.version}
                for item in summary.interfaces
            ]
            stored.verification = summary.verification.value
            stored.signing_key_id = summary.key_id
            stored.fetched_at = self._clock.now()
            await audit.append(
                session,
                tenant_id,
                AuditRecord(
                    action="a2a_agent.card_read",
                    outcome=summary.verification.value,
                    actor_id=actor_id,
                    resource_type="a2a_agent",
                    resource_id=str(stored.id),
                    decision={
                        "card_sha256": digest,
                        "changed": changed,
                        "signing_key_id": summary.key_id,
                        "governability": self.governability(stored),
                    },
                ),
            )
            await session.flush()
            return stored

    # The allowlist

    async def grant(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        key: str,
        *,
        scope_type: ScopeType,
        scope_id: UUID | None,
    ) -> A2aGrant:
        if scope_type not in _GRANT_SCOPES:
            raise ConflictError("a grant is given to the tenant, a project or an AI system")
        target = tenant_id if scope_type is ScopeType.TENANT else scope_id
        if target is None:
            raise ConflictError(f"a grant to a {scope_type.value} needs its id")
        agent = await self.get(session, tenant_id, key)
        existing = await session.scalar(
            select(A2aGrant).where(
                A2aGrant.agent_id == agent.id,
                A2aGrant.scope_type == scope_type.value,
                A2aGrant.scope_id == target,
            )
        )
        if existing is not None:
            return existing
        grant = A2aGrant(
            tenant_id=tenant_id,
            agent_id=agent.id,
            scope_type=scope_type.value,
            scope_id=target,
            created_at=self._clock.now(),
        )
        session.add(grant)
        await session.flush()
        return grant

    async def grants(
        self, session: AsyncSession, tenant_id: UUID, key: str | None = None
    ) -> Sequence[tuple[A2aGrant, str]]:
        """Grants with the key of their agent, of one agent or of the tenant."""
        query = (
            select(A2aGrant, A2aAgent.key)
            .join(A2aAgent, A2aAgent.id == A2aGrant.agent_id)
            .where(A2aGrant.tenant_id == tenant_id)
            .order_by(A2aAgent.key, A2aGrant.scope_type, A2aGrant.id)
        )
        if key is not None:
            query = query.where(A2aAgent.key == key)
        return [(grant, agent_key) for grant, agent_key in await session.execute(query)]

    async def revoke(self, session: AsyncSession, tenant_id: UUID, grant_id: UUID) -> A2aGrant:
        grant = await session.scalar(
            select(A2aGrant).where(A2aGrant.tenant_id == tenant_id, A2aGrant.id == grant_id)
        )
        if grant is None:
            raise NotFoundError(f"grant {grant_id} not found")
        await session.delete(grant)
        await session.flush()
        return grant

    async def allows(self, session: AsyncSession, agent: A2aAgent, caller: Caller) -> bool:
        """Whether the caller may call the agent. Nothing is allowed until a grant says so."""
        scopes = [
            (A2aGrant.scope_type == ScopeType.TENANT.value)
            & (A2aGrant.scope_id == caller.tenant_id)
        ]
        if caller.project_id is not None:
            scopes.append(
                (A2aGrant.scope_type == ScopeType.PROJECT.value)
                & (A2aGrant.scope_id == caller.project_id)
            )
        if caller.ai_system_id is not None:
            scopes.append(
                (A2aGrant.scope_type == ScopeType.AI_SYSTEM.value)
                & (A2aGrant.scope_id == caller.ai_system_id)
            )
        found = await session.scalar(
            select(A2aGrant.id)
            .where(
                A2aGrant.tenant_id == caller.tenant_id, A2aGrant.agent_id == agent.id, or_(*scopes)
            )
            .limit(1)
        )
        return found is not None
