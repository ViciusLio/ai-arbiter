"""The MCP proxy: decide, record, then forward (ADR-0047, ADR-0049).

A call goes through three steps. First, in one transaction, the proxy looks the server
up, asks the allowlist and the inventory, lets the rule pack decide, and writes the
decision to the audit log together with a row for the call: if that cannot be written,
nothing is forwarded. Then, with no transaction open, the request is sent on. Last, the
row is completed with how the call ended.

The proxy never reads the arguments of a call or its result, and stores neither. The one
answer it reads is the list of tools, and of that only the names: a caller is shown the
tools its grants let it call.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ai_arbiter import __version__
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.config.settings import McpSettings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.errors import ArbiterError, ConflictError, MissingExtraError
from ai_arbiter.core.invocation import Invocation, InvocationOutcome, InvocationProtocol
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.ports import AuditLog, SecretStore, SystemDirectory
from ai_arbiter.core.rules import Decision, Facts, RulePack, load_packaged_pack, load_rule_pack
from ai_arbiter.gateway.identity.service import AuthenticatedKey
from ai_arbiter.gateway.mcp.catalogue import (
    MODERN_REVISION,
    Caller,
    Governability,
    McpCatalogue,
    governability,
)
from ai_arbiter.gateway.mcp.model import McpServer
from ai_arbiter.gateway.mcp.protocol import (
    LISTING_METHODS,
    METHOD_HEADER,
    PROTOCOL_HEADER,
    TOOL_CALL,
    TOOL_LIST,
    McpRequest,
    forwarded_headers,
    read_response,
    types,
)
from ai_arbiter.gateway.policy.engine import PolicyOutcome, decide

logger = logging.getLogger(__name__)

MCP_PACK = "mcp"
STAGE = "mcp_call"
# What the catalogue records for a server that answers, but not as revision 2026-07-28
# does. Which earlier revisions it speaks is not asked: that needs a handshake.
LEGACY_MARKER = "legacy"
_MAX_TOOL_PAGES = 20


class UpstreamUnavailableError(ArbiterError):
    """The MCP server could not be reached, or answered in a way that cannot be relayed."""

    def __init__(self, reason: str) -> None:
        super().__init__("the MCP server could not be reached or did not answer as expected")
        self.reason = reason


def load_mcp_pack(settings: McpSettings) -> RulePack:
    if settings.pack is not None:
        return load_rule_pack(settings.pack)
    return load_packaged_pack(MCP_PACK)


@dataclass(frozen=True)
class Prepared:
    """A call after the decision: what was decided, and where it goes if allowed."""

    invocation_id: UUID
    tenant_id: UUID
    decision: Decision
    request: McpRequest
    url: str | None
    credential: str | None
    started: float
    # For an answer to tools/list: the tools to keep in it. None keeps them all.
    visible_tools: frozenset[str] | None = None

    @property
    def allowed(self) -> bool:
        return self.decision.outcome != PolicyOutcome.DENY.value


class McpProxy:
    def __init__(
        self,
        *,
        database: Database,
        catalogue: McpCatalogue,
        pack: RulePack,
        audit: AuditLog,
        secrets: SecretStore,
        settings: McpSettings,
        systems: SystemDirectory,
        clock: Clock | None = None,
        transport: Any = None,
    ) -> None:
        self._database = database
        self._catalogue = catalogue
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
                raise MissingExtraError("gateway", "The MCP proxy") from exc
            # Redirects are never followed: a server of the catalogue must not be able
            # to send a request, with its credential, somewhere the catalogue never named.
            self._client = httpx.AsyncClient(transport=self._transport, follow_redirects=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # Decide and record

    async def authorize(
        self, key: AuthenticatedKey, server_key: str, request: McpRequest, request_bytes: int
    ) -> Prepared:
        """Decide whether the call may go on, and write the decision and the call down.

        Everything happens in one transaction: a call that is not in the audit log is
        not forwarded.
        """
        context = key.context
        caller = Caller(context.tenant_id, context.project_id, context.ai_system_id)
        async with self._database.transaction() as session:
            server = await self._catalogue.find(session, context.tenant_id, server_key)
            granted = False
            visible: frozenset[str] | None = None
            if server is not None:
                granted = await self._catalogue.allows(
                    session,
                    server,
                    caller,
                    request.tool,
                    whole_server=request.method != TOOL_CALL
                    and request.method not in LISTING_METHODS,
                )
                if granted and request.method == TOOL_LIST and self._settings.filter_tool_list:
                    visible = await self._catalogue.callable_tools(session, server, caller)
            system = await self._systems.resolve(session, context.tenant_id, context.ai_system_id)
            declared = system.ai_system_id is not None
            facts: Facts = {
                "server.known": server is not None,
                "server.governability": governability(server) if server is not None else None,
                "call.method": request.method,
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
                        "server_id": str(server.id) if server is not None else None,
                        "method": request.method[:100],
                        "name": request.recorded_name,
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
                    protocol=InvocationProtocol.MCP.value,
                    target=server_key[:100],
                    target_known=server is not None,
                    method=request.method[:100],
                    name=(request.recorded_name or "")[:200] or None,
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
                    action="mcp.call",
                    actor_id=context.principal_id,
                    resource_type="invocation",
                    resource_id=str(invocation_id),
                ),
            )
            return Prepared(
                invocation_id=invocation_id,
                tenant_id=context.tenant_id,
                decision=decision,
                request=request,
                url=server.url if server is not None else None,
                credential=server.credential if server is not None else None,
                started=time.monotonic(),
                visible_tools=visible,
            )

    # Forward

    async def _upstream_headers(
        self, headers: dict[str, str], credential: str | None
    ) -> dict[str, str]:
        if credential is not None:
            token = await self._secrets.get(SecretRef.parse(credential))
            headers["authorization"] = f"Bearer {token.get_secret_value()}"
        return headers

    async def forward(self, prepared: Prepared, body: bytes, headers: dict[str, str]) -> Any:
        """Send the request on and return the open response, to be read by the caller.

        No database transaction is open here. Raises ``UpstreamUnavailableError``.
        """
        import httpx

        if prepared.url is None:
            raise UpstreamUnavailableError("NoUrl")
        client = self._http()
        timeout = httpx.Timeout(
            self._settings.timeout_seconds, read=self._settings.stream_idle_seconds
        )
        try:
            request = client.build_request(
                "POST",
                prepared.url,
                content=body,
                headers=await self._upstream_headers(
                    forwarded_headers(headers), prepared.credential
                ),
                timeout=timeout,
            )
            response = await client.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise UpstreamUnavailableError(type(exc).__name__) from exc
        if 300 <= response.status_code < 400:
            await response.aclose()
            raise UpstreamUnavailableError("Redirect")
        return response

    async def complete(
        self,
        prepared: Prepared,
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
                "could not record how an MCP call ended",
                extra={"invocation_id": str(prepared.invocation_id)},
            )

    # Ask a server what it is

    def _meta(self, mcp: Any) -> dict[str, Any]:
        return {
            mcp.PROTOCOL_VERSION_META_KEY: MODERN_REVISION,
            mcp.CLIENT_INFO_META_KEY: {"name": "arbiter", "version": __version__},
            mcp.CLIENT_CAPABILITIES_META_KEY: {},
        }

    async def _ask(
        self, server: McpServer, method: str, params: dict[str, Any], request_id: int
    ) -> tuple[int, dict[str, Any] | None]:
        import httpx

        mcp = types()
        body = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": {**params, "_meta": self._meta(mcp)},
        }
        headers = await self._upstream_headers(
            forwarded_headers({PROTOCOL_HEADER: MODERN_REVISION, METHOD_HEADER: method}),
            server.credential,
        )
        try:
            response = await self._http().post(
                server.url, json=body, headers=headers, timeout=self._settings.timeout_seconds
            )
        except httpx.HTTPError as exc:
            raise ConflictError(
                f"the server '{server.key}' could not be reached ({type(exc).__name__})"
            ) from exc
        if len(response.content) > self._settings.max_response_bytes:
            raise ConflictError(f"the server '{server.key}' answered with too large a body")
        content_type = response.headers.get("content-type", "")
        return response.status_code, read_response(content_type, response.content)

    async def discover(
        self, tenant_id: UUID, server_key: str, *, actor_id: UUID | None = None
    ) -> McpServer:
        """Ask a server which revisions it speaks and which tools it lists, and store it.

        The requests are made with no transaction open. Raises ``ConflictError`` when the
        server cannot be asked or cannot be reached.
        """
        mcp = types()
        async with self._database.session() as session:
            server = await self._catalogue.get(session, tenant_id, server_key)
        if governability(server) in (Governability.NOT_PROXIED, Governability.DISABLED):
            raise ConflictError(
                f"the server '{server_key}' is {governability(server)}: the proxy does not ask it"
            )

        status, answer = await self._ask(server, "server/discover", {}, 1)
        error = answer.get("error") if answer is not None else None
        result = answer.get("result") if answer is not None else None
        tools: list[str] | None = None
        if status == 200 and isinstance(result, dict):
            versions = list(mcp.DiscoverResult.model_validate(result).supported_versions)
        elif (
            isinstance(error, dict)
            and error.get("code") == mcp.UNSUPPORTED_PROTOCOL_VERSION
            and isinstance(error.get("data"), dict)
        ):
            versions = [str(item) for item in error["data"].get("supported") or []]
        elif 400 <= status < 500:
            # It answers, and not as a server of this revision would.
            versions = [LEGACY_MARKER]
        else:
            raise ConflictError(
                f"the server '{server_key}' did not answer the discovery (HTTP {status})"
            )

        if MODERN_REVISION in versions:
            tools = []
            cursor: str | None = None
            for page in range(_MAX_TOOL_PAGES):
                params = {"cursor": cursor} if cursor else {}
                status, answer = await self._ask(server, "tools/list", params, page + 2)
                listed = answer.get("result") if answer is not None else None
                if status != 200 or not isinstance(listed, dict):
                    # A server without tools may not implement the method at all.
                    break
                parsed = mcp.ListToolsResult.model_validate(listed)
                tools += [tool.name for tool in parsed.tools]
                cursor = parsed.next_cursor
                if not cursor:
                    break

        async with self._database.transaction() as session:
            stored = await self._catalogue.get(session, tenant_id, server_key)
            await self._catalogue.record_discovery(
                session, stored, protocol_versions=versions, tools=tools
            )
            await self._audit.append(
                session,
                tenant_id,
                AuditRecord(
                    action="mcp_server.discovered",
                    outcome=governability(stored),
                    actor_id=actor_id,
                    resource_type="mcp_server",
                    resource_id=str(stored.id),
                ),
            )
            return stored
