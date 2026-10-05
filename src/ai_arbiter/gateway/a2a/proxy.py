"""The A2A proxy: decide, record, then forward (ADR-0051).

The same three steps as for MCP. In one transaction the proxy looks the agent up, asks
the allowlist and the inventory, lets the rule pack decide, and writes the decision to
the audit log with a row for the call: if that cannot be written, nothing is forwarded.
Then, with no transaction open, the request is sent to the interface the card lists for
the binding it came in on. Last, the row is completed with how the call ended.

What is said to an agent and what it answers is never read and never stored.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.config.settings import A2aSettings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.errors import ArbiterError, MissingExtraError
from ai_arbiter.core.invocation import Invocation, InvocationOutcome, InvocationProtocol
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.ports import AuditLog, SecretStore, SystemDirectory
from ai_arbiter.core.rules import Decision, Facts, RulePack, load_packaged_pack, load_rule_pack
from ai_arbiter.gateway.a2a.protocol import forwarded_headers
from ai_arbiter.gateway.a2a.registry import A2aRegistry
from ai_arbiter.gateway.identity.service import AuthenticatedKey
from ai_arbiter.gateway.mcp.catalogue import Caller
from ai_arbiter.gateway.policy.engine import PolicyOutcome, decide

logger = logging.getLogger(__name__)

A2A_PACK = "a2a"
STAGE = "a2a_call"


class AgentUnavailableError(ArbiterError):
    """The agent could not be reached, or answered in a way that cannot be relayed."""

    def __init__(self, reason: str) -> None:
        super().__init__("the agent could not be reached or did not answer as expected")
        self.reason = reason


def load_a2a_pack(settings: A2aSettings) -> RulePack:
    if settings.pack is not None:
        return load_rule_pack(settings.pack)
    return load_packaged_pack(A2A_PACK)


@dataclass(frozen=True)
class PreparedCall:
    """A call after the decision: what was decided, and where it goes if allowed."""

    invocation_id: UUID
    decision: Decision
    # The address of the agent's interface for the binding of the request.
    interface_url: str | None
    credential: str | None
    started: float

    @property
    def allowed(self) -> bool:
        return self.decision.outcome != PolicyOutcome.DENY.value


class A2aProxy:
    def __init__(
        self,
        *,
        database: Database,
        registry: A2aRegistry,
        pack: RulePack,
        audit: AuditLog,
        secrets: SecretStore,
        settings: A2aSettings,
        systems: SystemDirectory,
        clock: Clock | None = None,
        transport: Any = None,
    ) -> None:
        self._database = database
        self._registry = registry
        self.pack = pack
        self._audit = audit
        self._secrets = secrets
        self._settings = settings
        self._systems = systems
        self._clock = clock if clock is not None else SystemClock()
        self._transport = transport
        self._client: Any = None

    def _http(self) -> Any:
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise MissingExtraError("gateway", "The A2A proxy") from exc
            # Redirects are never followed: an agent must not be able to send a request,
            # with its credential, somewhere its card never named.
            self._client = httpx.AsyncClient(transport=self._transport, follow_redirects=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def authorize(
        self,
        key: AuthenticatedKey,
        agent_key: str,
        *,
        binding: str,
        operation: str,
        request_bytes: int,
    ) -> PreparedCall:
        """Decide whether the call may go on, and write the decision and the call down.

        Everything happens in one transaction: a call that is not in the audit log is
        not forwarded.
        """
        context = key.context
        caller = Caller(context.tenant_id, context.project_id, context.ai_system_id)
        async with self._database.transaction() as session:
            agent = await self._registry.find(session, context.tenant_id, agent_key)
            granted = False
            interface_url: str | None = None
            if agent is not None:
                granted = await self._registry.allows(session, agent, caller)
                interface_url = next(
                    (
                        item["url"]
                        for item in self._registry.usable_interfaces(agent)
                        if item["binding"] == binding
                    ),
                    None,
                )
            system = await self._systems.resolve(session, context.tenant_id, context.ai_system_id)
            declared = system.ai_system_id is not None
            facts: Facts = {
                "agent.known": agent is not None,
                "agent.governability": (
                    self._registry.governability(agent) if agent is not None else None
                ),
                "agent.verification": agent.verification if agent is not None else None,
                "agent.binding_offered": interface_url is not None if agent is not None else None,
                "call.operation": operation,
                "call.granted": granted,
                "system.declared": declared,
                "system.tier": system.tier.value if declared else None,
                "system.reviewed": system.reviewed if declared else None,
            }
            decision = decide(self.pack, STAGE, facts)
            invocation_id = new_id()
            denied = decision.outcome == PolicyOutcome.DENY.value
            decision = decision.model_copy(
                update={
                    "details": {
                        **decision.details,
                        "invocation_id": str(invocation_id),
                        "agent_id": str(agent.id) if agent is not None else None,
                        "binding": binding,
                        "operation": operation,
                        "card_verification": agent.verification if agent is not None else None,
                    }
                }
            )
            session.add(
                Invocation(
                    id=invocation_id,
                    tenant_id=context.tenant_id,
                    team_id=context.team_id,
                    project_id=context.project_id,
                    principal_id=context.principal_id,
                    ai_system_id=context.ai_system_id,
                    protocol=InvocationProtocol.A2A.value,
                    target=agent_key[:100],
                    target_known=agent is not None,
                    method=operation,
                    outcome=(
                        InvocationOutcome.DENIED.value
                        if denied
                        else InvocationOutcome.FORWARDED.value
                    ),
                    reason=decision.matches[0].rule_id if denied and decision.matches else None,
                    request_bytes=request_bytes,
                    started_at=self._clock.now(),
                    decision_id=decision.id,
                )
            )
            await self._audit.append(
                session,
                context.tenant_id,
                AuditRecord.of_decision(
                    decision,
                    action="a2a.call",
                    actor_id=context.principal_id,
                    resource_type="invocation",
                    resource_id=str(invocation_id),
                ),
            )
            return PreparedCall(
                invocation_id=invocation_id,
                decision=decision,
                interface_url=interface_url,
                credential=agent.credential if agent is not None else None,
                started=time.monotonic(),
            )

    async def forward(
        self,
        prepared: PreparedCall,
        *,
        verb: str,
        path: str,
        query: str,
        body: bytes,
        headers: dict[str, str],
    ) -> Any:
        """Send the request to the agent and return the open response.

        ``path`` is appended to the interface for the HTTP+JSON binding and is empty for
        JSON-RPC. No database transaction is open here. Raises ``AgentUnavailableError``.
        """
        import httpx

        if prepared.interface_url is None:
            raise AgentUnavailableError("NoInterface")
        url = prepared.interface_url
        if path:
            url = f"{url.rstrip('/')}/{path}"
        if query:
            url = f"{url}?{query}"
        sent = forwarded_headers(headers)
        if prepared.credential is not None:
            token = await self._secrets.get(SecretRef.parse(prepared.credential))
            sent["authorization"] = f"Bearer {token.get_secret_value()}"
        timeout = httpx.Timeout(
            self._settings.timeout_seconds, read=self._settings.stream_idle_seconds
        )
        client = self._http()
        try:
            request = client.build_request(
                verb, url, content=body or None, headers=sent, timeout=timeout
            )
            response = await client.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise AgentUnavailableError(type(exc).__name__) from exc
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise AgentUnavailableError("Redirect")
        return response

    async def complete(
        self,
        prepared: PreparedCall,
        *,
        status_code: int | None,
        response_bytes: int | None,
        streamed: bool,
        reason: str | None = None,
    ) -> None:
        """Write how a forwarded call ended. The decision is already in the audit log."""
        failed = reason is not None or status_code is None or status_code >= 400
        try:
            async with self._database.transaction() as session:
                row = await session.get(Invocation, prepared.invocation_id)
                if row is None:
                    return
                row.outcome = (
                    InvocationOutcome.ERROR.value if failed else InvocationOutcome.OK.value
                )
                row.reason = reason or (f"http_{status_code}" if failed else None)
                row.status_code = status_code
                row.response_bytes = response_bytes
                row.streamed = streamed
                row.duration_ms = int((time.monotonic() - prepared.started) * 1000)
        except Exception:
            # The call was made and the decision is recorded; only its ending is lost.
            logger.exception(
                "could not record how an A2A call ended",
                extra={"invocation_id": str(prepared.invocation_id)},
            )
