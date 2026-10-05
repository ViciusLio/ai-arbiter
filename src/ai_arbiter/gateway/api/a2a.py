"""Control plane of the A2A registry: agents, their card, and who may call them."""

from datetime import datetime
from functools import partial
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.agents import HTTP_JSON_BINDING, JSONRPC_BINDING
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.i18n import Translator, negotiate
from ai_arbiter.gateway.a2a.model import A2aAgent, A2aGrant
from ai_arbiter.gateway.a2a.protocol import (
    DENIED,
    A2aRequestError,
    jsonrpc_error,
    parse_jsonrpc,
    rest_operation,
)
from ai_arbiter.gateway.a2a.proxy import AgentUnavailableError, PreparedCall
from ai_arbiter.gateway.api.compliance import Compliance
from ai_arbiter.gateway.api.deps import Admin, Caller, Reader, Runtime
from ai_arbiter.gateway.api.errors import problem
from ai_arbiter.gateway.api.relay import relay
from ai_arbiter.gateway.identity.model import ScopeType
from ai_arbiter.gateway.identity.service import AuthenticatedKey
from ai_arbiter.gateway.runtime import GatewayRuntime

admin_router = APIRouter(prefix="/api/v1/a2a", tags=["a2a"])


class AgentIn(BaseModel):
    key: str
    name: str
    # Where the Agent Card is read from, for example
    # https://agent.example.org/.well-known/agent-card.json
    card_url: str
    # Key of the declared AI system the agent belongs to.
    ai_system: str | None = None
    # A secret reference (secret://NAME) for the credential sent to the agent.
    credential: str | None = None


class InterfaceOut(BaseModel):
    binding: str
    url: str
    version: str
    # Whether a proxy may forward to it: a binding it speaks, on the host of the card.
    usable: bool


class AgentOut(BaseModel):
    key: str
    name: str
    card_url: str
    ai_system_id: UUID | None
    has_credential: bool
    enabled: bool
    # governable, not_fetched, no_proxied_binding or disabled.
    governability: str
    # verified, unsigned, unknown_key, invalid or not_fetched.
    verification: str
    signing_key_id: str | None
    card_name: str | None
    card_version: str | None
    card_sha256: str | None
    interfaces: list[InterfaceOut]
    fetched_at: datetime | None
    note: str = (
        "A verified card was signed with a key the operator configured. A key a card "
        "names for itself is never fetched."
    )


class GrantIn(BaseModel):
    scope_type: Literal["tenant", "project", "ai_system"] = "tenant"
    scope_id: UUID | None = None


class GrantOut(BaseModel):
    id: UUID
    agent: str
    scope_type: str
    scope_id: UUID


async def _audit(
    runtime: GatewayRuntime,
    session: AsyncSession,
    caller: AuthenticatedKey,
    action: str,
    resource_type: str,
    resource_id: object,
) -> None:
    await runtime.audit.append(
        session,
        caller.context.tenant_id,
        AuditRecord(
            action=action,
            outcome="ok",
            actor_id=caller.context.principal_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
        ),
    )


def _agent(runtime: GatewayRuntime, agent: A2aAgent) -> AgentOut:
    usable = {item["url"] for item in runtime.a2a.usable_interfaces(agent)}
    return AgentOut(
        key=agent.key,
        name=agent.name,
        card_url=agent.card_url,
        ai_system_id=agent.ai_system_id,
        has_credential=agent.credential is not None,
        enabled=agent.enabled,
        governability=runtime.a2a.governability(agent),
        verification=agent.verification,
        signing_key_id=agent.signing_key_id,
        card_name=agent.card_name,
        card_version=agent.card_version,
        card_sha256=agent.card_sha256,
        interfaces=[
            InterfaceOut(
                binding=str(item.get("binding")),
                url=str(item.get("url")),
                version=str(item.get("version") or ""),
                usable=str(item.get("url")) in usable,
            )
            for item in agent.interfaces or []
            if isinstance(item, dict)
        ],
        fetched_at=agent.fetched_at,
    )


def _grant(grant: A2aGrant, agent_key: str) -> GrantOut:
    return GrantOut(
        id=grant.id, agent=agent_key, scope_type=grant.scope_type, scope_id=grant.scope_id
    )


@admin_router.get("/agents", summary="List the agents of the registry")
async def list_agents(runtime: Runtime, caller: Reader) -> list[AgentOut]:
    async with runtime.database.session() as session:
        return [
            _agent(runtime, agent)
            for agent in await runtime.a2a.list(session, caller.context.tenant_id)
        ]


@admin_router.post(
    "/agents",
    summary="Register an A2A agent by the address of its card",
    description="The card must be at an https address. It is not read here: ask for it with "
    "`POST /agents/{key}/card`. Nobody may call an agent until a grant says so.",
    status_code=status.HTTP_201_CREATED,
)
async def register_agent(
    body: AgentIn, runtime: Runtime, compliance: Compliance, caller: Admin
) -> AgentOut:
    tenant_id = caller.context.tenant_id
    async with runtime.database.transaction() as session:
        system_id = None
        if body.ai_system is not None:
            system_id = (await compliance.inventory.get(session, tenant_id, body.ai_system)).id
        agent = await runtime.a2a.register(
            session,
            tenant_id,
            key=body.key,
            name=body.name,
            card_url=body.card_url,
            ai_system_id=system_id,
            credential=body.credential,
        )
        await _audit(runtime, session, caller, "a2a_agent.registered", "a2a_agent", agent.id)
        return _agent(runtime, agent)


@admin_router.get("/agents/{key}", summary="An agent with what its card said")
async def get_agent(key: str, runtime: Runtime, caller: Reader) -> AgentOut:
    async with runtime.database.session() as session:
        return _agent(runtime, await runtime.a2a.get(session, caller.context.tenant_id, key))


@admin_router.post(
    "/agents/{key}/card",
    summary="Read the Agent Card again and verify its signatures",
    description="The card is fetched from the registered address, without following "
    "redirects, and its signatures are verified against the keys of `a2a.trusted_keys`.",
)
async def read_card(key: str, runtime: Runtime, caller: Admin) -> AgentOut:
    agent = await runtime.a2a.refresh(
        runtime.database,
        runtime.audit,
        caller.context.tenant_id,
        key,
        actor_id=caller.context.principal_id,
    )
    return _agent(runtime, agent)


@admin_router.delete(
    "/agents/{key}",
    summary="Remove an agent with its grants",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_agent(key: str, runtime: Runtime, caller: Admin) -> Response:
    async with runtime.database.transaction() as session:
        agent = await runtime.a2a.remove(session, caller.context.tenant_id, key)
        await _audit(runtime, session, caller, "a2a_agent.removed", "a2a_agent", agent.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.post(
    "/agents/{key}/grants",
    summary="Allow the tenant, a project or an AI system to call an agent",
    status_code=status.HTTP_201_CREATED,
)
async def create_grant(key: str, body: GrantIn, runtime: Runtime, caller: Admin) -> GrantOut:
    async with runtime.database.transaction() as session:
        grant = await runtime.a2a.grant(
            session,
            caller.context.tenant_id,
            key,
            scope_type=ScopeType(body.scope_type),
            scope_id=body.scope_id,
        )
        await _audit(runtime, session, caller, "a2a_grant.created", "a2a_grant", grant.id)
    return _grant(grant, key)


@admin_router.get("/grants", summary="List the grants of the registry")
async def list_grants(runtime: Runtime, caller: Reader) -> list[GrantOut]:
    async with runtime.database.session() as session:
        return [
            _grant(grant, key)
            for grant, key in await runtime.a2a.grants(session, caller.context.tenant_id)
        ]


@admin_router.delete(
    "/grants/{grant_id}", summary="Withdraw a grant", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_grant(grant_id: UUID, runtime: Runtime, caller: Admin) -> Response:
    async with runtime.database.transaction() as session:
        grant = await runtime.a2a.revoke(session, caller.context.tenant_id, grant_id)
        await _audit(runtime, session, caller, "a2a_grant.revoked", "a2a_grant", grant.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- data plane --------------------------------------------------------------------------

proxy_router = APIRouter(tags=["a2a"])

_DESCRIPTION = (
    "Authenticate with an Arbiter API key; the agent receives the credential of the "
    "registry, never the caller's. A call is forwarded only if a grant allows it, and "
    "every call is written to the audit log without what was said."
)


async def _body(request: Request, limit: int) -> bytes | None:
    """The request body, or ``None`` when it is larger than ``limit``."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        return None
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            return None
    return body


def _denial(prepared: PreparedCall, request: Request) -> tuple[int, str, dict[str, Any]]:
    rules = [match.rule_id for match in prepared.decision.matches]
    translator = Translator(negotiate(request.headers.get("accept-language")))
    code = status.HTTP_404_NOT_FOUND if "A2A-AGENT-UNKNOWN" in rules else status.HTTP_403_FORBIDDEN
    message = translator.text(prepared.decision.matches[0].message_key)
    return code, message, {"rules": rules, "decision_id": str(prepared.decision.id)}


@proxy_router.post(
    "/a2a/{agent_key}",
    summary="Call an agent of the registry through its JSON-RPC binding",
    description="The JSON-RPC endpoint of an agent, for the operations A2A 1.0 defines. "
    + _DESCRIPTION,
    response_model=None,
)
async def call_agent_jsonrpc(
    agent_key: str, request: Request, runtime: Runtime, caller: Caller
) -> Response:
    settings = runtime.settings.a2a
    proxy = runtime.a2a_proxy

    def error(
        code: int, rpc: int, message: str, request_id: int | str | None = None, **data: Any
    ) -> JSONResponse:
        return JSONResponse(
            jsonrpc_error(rpc, message, request_id=request_id, data=data or None),
            status_code=code,
        )

    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins:
        return error(status.HTTP_403_FORBIDDEN, DENIED, "this origin is not allowed")
    body = await _body(request, settings.max_request_bytes)
    if body is None:
        return error(status.HTTP_413_CONTENT_TOO_LARGE, DENIED, "the request is too large")
    try:
        call = parse_jsonrpc(body)
    except A2aRequestError as problem_found:
        return error(
            problem_found.status,
            problem_found.code,
            str(problem_found),
            problem_found.request_id,
        )

    prepared = await proxy.authorize(
        caller,
        agent_key,
        binding=JSONRPC_BINDING,
        operation=call.operation,
        request_bytes=len(body),
    )
    if not prepared.allowed:
        code, message, data = _denial(prepared, request)
        return error(code, DENIED, message, call.request_id, **data)
    headers = {name.lower(): value for name, value in request.headers.items()}
    try:
        upstream = await proxy.forward(
            prepared, verb="POST", path="", query="", body=body, headers=headers
        )
    except AgentUnavailableError as unavailable:
        await proxy.complete(
            prepared,
            status_code=None,
            response_bytes=None,
            streamed=False,
            reason=unavailable.reason,
        )
        return error(status.HTTP_502_BAD_GATEWAY, DENIED, str(unavailable), call.request_id)
    return await relay(
        upstream,
        max_bytes=settings.max_response_bytes,
        complete=partial(proxy.complete, prepared),
        failure=lambda: error(
            status.HTTP_502_BAD_GATEWAY,
            DENIED,
            "the answer of the agent could not be relayed",
            call.request_id,
        ),
    )


@proxy_router.api_route(
    "/a2a/{agent_key}/rest/{path:path}",
    methods=["GET", "POST", "DELETE"],
    summary="Call an agent of the registry through its HTTP+JSON binding",
    description="The HTTP+JSON interface of an agent, for the URL patterns A2A 1.0 defines "
    "(`message:send`, `tasks/{id}`, ...). " + _DESCRIPTION,
    response_model=None,
)
async def call_agent_rest(
    agent_key: str, path: str, request: Request, runtime: Runtime, caller: Caller
) -> Response:
    settings = runtime.settings.a2a
    proxy = runtime.a2a_proxy
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.allowed_origins:
        return problem(status.HTTP_403_FORBIDDEN, "denied", "Denied", "this origin is not allowed")
    operation = rest_operation(request.method, path)
    if operation is None:
        return problem(
            status.HTTP_404_NOT_FOUND,
            "not_found",
            "Not found",
            "this is not an operation of the A2A HTTP+JSON binding",
        )
    body = await _body(request, settings.max_request_bytes)
    if body is None:
        return problem(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "too_large",
            "Request too large",
            "the request is too large",
        )

    prepared = await proxy.authorize(
        caller,
        agent_key,
        binding=HTTP_JSON_BINDING,
        operation=operation,
        request_bytes=len(body),
    )
    if not prepared.allowed:
        code, message, data = _denial(prepared, request)
        return problem(code, "denied", "Denied", message, **data)
    headers = {name.lower(): value for name, value in request.headers.items()}
    try:
        upstream = await proxy.forward(
            prepared,
            verb=request.method,
            path=path,
            query=request.url.query,
            body=body,
            headers=headers,
        )
    except AgentUnavailableError as unavailable:
        await proxy.complete(
            prepared,
            status_code=None,
            response_bytes=None,
            streamed=False,
            reason=unavailable.reason,
        )
        return problem(
            status.HTTP_502_BAD_GATEWAY, "upstream_error", "Agent unavailable", str(unavailable)
        )
    return await relay(
        upstream,
        max_bytes=settings.max_response_bytes,
        complete=partial(proxy.complete, prepared),
        failure=lambda: problem(
            status.HTTP_502_BAD_GATEWAY,
            "upstream_error",
            "Agent unavailable",
            "the answer of the agent could not be relayed",
        ),
    )
