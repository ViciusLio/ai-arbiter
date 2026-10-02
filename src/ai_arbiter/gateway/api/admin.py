"""Control plane: identity, budgets, usage and the audit log.

Every change is written to the audit chain in the transaction that makes it. Entries name
what changed by identifier, never by name.
"""

from collections.abc import AsyncIterator
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.audit import AuditRecord, set_tenant_fail_mode, tenant_fail_mode
from ai_arbiter.core.config.settings import parse_decimal
from ai_arbiter.core.domain.tenancy import AccessRole
from ai_arbiter.core.errors import ConflictError
from ai_arbiter.core.i18n import SUPPORTED_LOCALES
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.gateway.api.deps import Admin, AnyKey, Reader, Runtime
from ai_arbiter.gateway.finops.budgets import BudgetPeriod
from ai_arbiter.gateway.finops.report import render_usage_report
from ai_arbiter.gateway.finops.usage import usage_report
from ai_arbiter.gateway.identity.keys import display_prefix
from ai_arbiter.gateway.identity.model import ApiKey, PrincipalKind, ScopeType
from ai_arbiter.gateway.identity.service import AuthenticatedKey
from ai_arbiter.gateway.runtime import GatewayRuntime

router = APIRouter(prefix="/api/v1")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


async def _audit(
    runtime: GatewayRuntime,
    session: AsyncSession,
    caller: AuthenticatedKey,
    action: str,
    resource_type: str,
    resource_id: object,
    outcome: str = "ok",
) -> None:
    await runtime.audit.append(
        session,
        caller.context.tenant_id,
        AuditRecord(
            action=action,
            outcome=outcome,
            actor_id=caller.context.principal_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
        ),
    )


# --- who am I ----------------------------------------------------------------------------


class Me(BaseModel):
    tenant_id: UUID
    principal_id: UUID | None
    team_id: UUID | None
    project_id: UUID | None
    ai_system_id: UUID | None
    key_id: str
    roles: list[AccessRole]


@router.get("/me", tags=["identity"], summary="The caller, as the gateway sees it")
async def me(caller: AnyKey) -> Me:
    context = caller.context
    return Me(
        tenant_id=context.tenant_id,
        principal_id=context.principal_id,
        team_id=context.team_id,
        project_id=context.project_id,
        ai_system_id=context.ai_system_id,
        key_id=caller.key_id,
        roles=sorted(context.roles),
    )


# --- teams and projects ------------------------------------------------------------------


class TeamIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TeamOut(_Out):
    id: UUID
    name: str
    created_at: datetime


class ProjectIn(BaseModel):
    team_id: UUID
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(_Out):
    id: UUID
    team_id: UUID
    name: str
    created_at: datetime


@router.get("/teams", tags=["identity"], summary="List teams")
async def list_teams(runtime: Runtime, caller: Admin) -> list[TeamOut]:
    async with runtime.database.session() as session:
        teams = await runtime.identity.list_teams(session, caller.context.tenant_id)
    return [TeamOut.model_validate(team) for team in teams]


@router.post(
    "/teams", tags=["identity"], summary="Create a team", status_code=status.HTTP_201_CREATED
)
async def create_team(body: TeamIn, runtime: Runtime, caller: Admin) -> TeamOut:
    async with runtime.database.transaction() as session:
        team = await runtime.identity.create_team(session, caller.context.tenant_id, body.name)
        await _audit(runtime, session, caller, "team.created", "team", team.id)
    return TeamOut.model_validate(team)


@router.get("/projects", tags=["identity"], summary="List projects")
async def list_projects(runtime: Runtime, caller: Admin) -> list[ProjectOut]:
    async with runtime.database.session() as session:
        projects = await runtime.identity.list_projects(session, caller.context.tenant_id)
    return [ProjectOut.model_validate(project) for project in projects]


@router.post(
    "/projects",
    tags=["identity"],
    summary="Create a project",
    status_code=status.HTTP_201_CREATED,
)
async def create_project(body: ProjectIn, runtime: Runtime, caller: Admin) -> ProjectOut:
    async with runtime.database.transaction() as session:
        project = await runtime.identity.create_project(
            session, caller.context.tenant_id, body.team_id, body.name
        )
        await _audit(runtime, session, caller, "project.created", "project", project.id)
    return ProjectOut.model_validate(project)


# --- principals and roles ----------------------------------------------------------------


class PrincipalIn(BaseModel):
    kind: PrincipalKind
    display_name: str = Field(min_length=1, max_length=200)
    external_id: str | None = Field(default=None, max_length=200)


class PrincipalOut(_Out):
    id: UUID
    kind: str
    display_name: str
    external_id: str | None
    created_at: datetime


class RoleIn(BaseModel):
    role: AccessRole
    scope_type: Literal["tenant", "team", "project"] = "tenant"
    scope_id: UUID | None = None


class RoleOut(_Out):
    id: UUID
    principal_id: UUID
    role: str
    scope_type: str
    scope_id: UUID


@router.get("/principals", tags=["identity"], summary="List principals")
async def list_principals(runtime: Runtime, caller: Admin) -> list[PrincipalOut]:
    async with runtime.database.session() as session:
        principals = await runtime.identity.list_principals(session, caller.context.tenant_id)
    return [PrincipalOut.model_validate(principal) for principal in principals]


@router.post(
    "/principals",
    tags=["identity"],
    summary="Create a principal: a person or a service",
    status_code=status.HTTP_201_CREATED,
)
async def create_principal(body: PrincipalIn, runtime: Runtime, caller: Admin) -> PrincipalOut:
    async with runtime.database.transaction() as session:
        principal = await runtime.identity.create_principal(
            session,
            caller.context.tenant_id,
            kind=body.kind,
            display_name=body.display_name,
            external_id=body.external_id,
        )
        await _audit(runtime, session, caller, "principal.created", "principal", principal.id)
    return PrincipalOut.model_validate(principal)


@router.post(
    "/principals/{principal_id}/roles",
    tags=["identity"],
    summary="Grant a role on the tenant, a team or a project",
    status_code=status.HTTP_201_CREATED,
)
async def grant_role(principal_id: UUID, body: RoleIn, runtime: Runtime, caller: Admin) -> RoleOut:
    async with runtime.database.transaction() as session:
        binding = await runtime.identity.grant_role(
            session,
            caller.context.tenant_id,
            principal_id=principal_id,
            role=body.role,
            scope_type=ScopeType(body.scope_type),
            scope_id=body.scope_id,
        )
        await _audit(
            runtime, session, caller, "role.granted", "principal", principal_id, body.role.value
        )
    return RoleOut.model_validate(binding)


# --- API keys ----------------------------------------------------------------------------


class ApiKeyIn(BaseModel):
    project_id: UUID
    principal_id: UUID
    name: str = Field(min_length=1, max_length=200)
    ai_system_id: UUID | None = None
    expires_at: datetime | None = None


class ApiKeyOut(_Out):
    key_id: str
    prefix: str
    name: str
    project_id: UUID
    principal_id: UUID
    ai_system_id: UUID | None
    created_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class ApiKeyIssued(ApiKeyOut):
    # Shown in this response only. It cannot be retrieved later.
    key: str


def _key_out(row: ApiKey) -> ApiKeyOut:
    return ApiKeyOut(
        key_id=row.key_id,
        prefix=display_prefix(row.key_id),
        name=row.name,
        project_id=row.project_id,
        principal_id=row.principal_id,
        ai_system_id=row.ai_system_id,
        created_at=row.created_at,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )


@router.get("/api-keys", tags=["identity"], summary="List API keys, without the keys themselves")
async def list_api_keys(runtime: Runtime, caller: Admin) -> list[ApiKeyOut]:
    async with runtime.database.session() as session:
        keys = await runtime.identity.list_api_keys(session, caller.context.tenant_id)
    return [_key_out(key) for key in keys]


@router.post(
    "/api-keys",
    tags=["identity"],
    summary="Issue an API key",
    description="The key is returned once, in this response. Only a keyed hash of it is stored.",
    status_code=status.HTTP_201_CREATED,
)
async def issue_api_key(body: ApiKeyIn, runtime: Runtime, caller: Admin) -> ApiKeyIssued:
    if body.expires_at is not None and body.expires_at.tzinfo is None:
        raise ConflictError("expires_at must carry a time zone")
    async with runtime.database.transaction() as session:
        row, key = await runtime.identity.issue_api_key(
            session,
            caller.context.tenant_id,
            project_id=body.project_id,
            principal_id=body.principal_id,
            name=body.name,
            ai_system_id=body.ai_system_id,
            expires_at=body.expires_at,
        )
        await _audit(runtime, session, caller, "api_key.issued", "api_key", row.key_id)
    return ApiKeyIssued(**_key_out(row).model_dump(), key=key)


@router.delete("/api-keys/{key_id}", tags=["identity"], summary="Revoke an API key")
async def revoke_api_key(key_id: str, runtime: Runtime, caller: Admin) -> ApiKeyOut:
    async with runtime.database.transaction() as session:
        row = await runtime.identity.revoke_api_key(session, caller.context.tenant_id, key_id)
        await _audit(runtime, session, caller, "api_key.revoked", "api_key", row.key_id)
    return _key_out(row)


# --- budgets -----------------------------------------------------------------------------


class BudgetIn(BaseModel):
    scope_type: ScopeType
    scope_id: UUID | None = None
    period: BudgetPeriod
    # A decimal written as a string, for example "25.00".
    limit_amount: str
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    soft_threshold_percent: int = Field(default=80, ge=1, le=100)
    hard: bool = False


class BudgetOut(BaseModel):
    id: UUID
    scope_type: str
    scope_id: UUID
    period: str
    limit_amount: str
    currency: str
    soft_threshold_percent: int
    hard: bool
    spent: str
    level: str


def _amount(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


@router.get(
    "/budgets",
    tags=["finops"],
    summary="List budgets with what has been spent in the current period",
)
async def list_budgets(runtime: Runtime, caller: Reader) -> list[BudgetOut]:
    result: list[BudgetOut] = []
    async with runtime.database.session() as session:
        for budget in await runtime.budgets.list(session, caller.context.tenant_id):
            state = await runtime.budgets.state(session, budget)
            result.append(
                BudgetOut(
                    id=budget.id,
                    scope_type=budget.scope_type,
                    scope_id=budget.scope_id,
                    period=budget.period,
                    limit_amount=_amount(budget.limit_amount),
                    currency=budget.currency,
                    soft_threshold_percent=budget.soft_threshold_percent,
                    hard=budget.hard,
                    spent=_amount(state.spent),
                    level=state.level.value,
                )
            )
    return result


@router.post(
    "/budgets",
    tags=["finops"],
    summary="Create a budget",
    description="A hard budget denies requests once its limit is reached; a soft one only "
    "reports it. A burst of concurrent requests can overshoot a hard limit slightly.",
    status_code=status.HTTP_201_CREATED,
)
async def create_budget(body: BudgetIn, runtime: Runtime, caller: Admin) -> BudgetOut:
    try:
        limit = parse_decimal(body.limit_amount, positive=True)
    except ValueError as error:
        raise ConflictError(f"limit_amount: {error}") from error
    async with runtime.database.transaction() as session:
        budget = await runtime.budgets.create(
            session,
            caller.context.tenant_id,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            period=body.period,
            limit_amount=limit,
            currency=body.currency,
            soft_threshold_percent=body.soft_threshold_percent,
            hard=body.hard,
        )
        state = await runtime.budgets.state(session, budget)
        await _audit(runtime, session, caller, "budget.created", "budget", budget.id)
    return BudgetOut(
        id=budget.id,
        scope_type=budget.scope_type,
        scope_id=budget.scope_id,
        period=budget.period,
        limit_amount=_amount(budget.limit_amount),
        currency=budget.currency,
        soft_threshold_percent=budget.soft_threshold_percent,
        hard=budget.hard,
        spent=_amount(state.spent),
        level=state.level.value,
    )


@router.delete(
    "/budgets/{budget_id}",
    tags=["finops"],
    summary="Delete a budget",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_budget(budget_id: UUID, runtime: Runtime, caller: Admin) -> Response:
    async with runtime.database.transaction() as session:
        await runtime.budgets.delete(session, caller.context.tenant_id, budget_id)
        await _audit(runtime, session, caller, "budget.deleted", "budget", budget_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- usage -------------------------------------------------------------------------------


class UsageLineOut(BaseModel):
    scope_id: UUID
    name: str | None
    currency: str
    requests: int
    denied: int
    failed: int
    unpriced: int
    estimated: int
    input_tokens: int
    output_tokens: int
    cost_estimate: str
    estimated_cost: str


class UsageOut(BaseModel):
    scope_type: str
    start: date
    end: date
    price_catalogue_version: str
    currency: str
    lines: list[UsageLineOut]
    note: str = "Costs are estimates computed from the price catalogue, not invoices."


@router.get(
    "/usage",
    tags=["finops"],
    summary="Usage and estimated cost per scope",
    description="Totals between two days, inclusive; the current month by default. "
    "`format=markdown` returns the report as text, in English or Italian.",
    response_model=UsageOut,
)
async def usage(
    runtime: Runtime,
    caller: Reader,
    scope: ScopeType = ScopeType.PROJECT,
    start: date | None = None,
    end: date | None = None,
    format: Annotated[Literal["json", "markdown"], Query()] = "json",  # noqa: A002
    locale: Annotated[str, Query()] = "en",
) -> Response | UsageOut:
    if locale not in SUPPORTED_LOCALES:
        raise ConflictError(f"unsupported locale '{locale}'")
    now = runtime.clock.now()
    last = end or now.date()
    first = start or last.replace(day=1)
    if first > last:
        raise ConflictError("start is after end")
    async with runtime.database.session() as session:
        tenant = await session.get_one(Tenant, caller.context.tenant_id)
        report = await usage_report(session, tenant, scope, start=first, end=last, generated_at=now)
    if format == "markdown":
        text = render_usage_report(
            report, runtime.catalogue, locale=locale, reporting=runtime.settings.finops.reporting
        )
        return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")
    return UsageOut(
        scope_type=scope.value,
        start=first,
        end=last,
        price_catalogue_version=runtime.catalogue.version,
        currency=runtime.catalogue.currency,
        lines=[
            UsageLineOut(
                scope_id=line.scope_id,
                name=report.names.get(line.scope_id),
                currency=line.currency,
                requests=line.totals.requests,
                denied=line.totals.denied,
                failed=line.totals.failed,
                unpriced=line.totals.unpriced,
                estimated=line.totals.estimated,
                input_tokens=line.totals.input_tokens,
                output_tokens=line.totals.output_tokens,
                cost_estimate=_amount(line.totals.cost_estimate),
                estimated_cost=_amount(line.totals.estimated_cost),
            )
            for line in report.lines
        ],
    )


# --- audit -------------------------------------------------------------------------------


class AuditEntryOut(_Out):
    id: UUID
    seq: int
    occurred_at: datetime
    actor_id: UUID | None
    action: str
    resource_type: str | None
    resource_id: str | None
    outcome: str
    decision: dict[str, object] | None
    prev_hash: str
    entry_hash: str


class VerificationOut(BaseModel):
    ok: bool
    entries: int
    head_seq: int
    head_hash: str | None
    first_broken_seq: int | None
    problem: str | None
    note: str = (
        "A chain that verifies is internally consistent. That is evidence against partial "
        "changes, not proof that the whole chain was never rewritten."
    )


class FailModeIn(BaseModel):
    mode: Literal["closed", "open"]


class FailModeOut(BaseModel):
    mode: Literal["closed", "open"]


@router.get(
    "/audit/entries",
    tags=["audit"],
    summary="Read audit entries in order",
    description="Entries with a sequence number greater than `after`, oldest first.",
)
async def audit_entries(
    runtime: Runtime,
    caller: Reader,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEntryOut]:
    async with runtime.database.session() as session:
        entries = await runtime.audit.entries(
            session, caller.context.tenant_id, after_seq=after, limit=limit
        )
    return [AuditEntryOut.model_validate(entry) for entry in entries]


@router.get(
    "/audit/verify",
    tags=["audit"],
    summary="Recompute the hash chain and report the first broken link",
)
async def audit_verify(runtime: Runtime, caller: Reader) -> VerificationOut:
    async with runtime.database.session() as session:
        report = await runtime.audit.verify(session, caller.context.tenant_id)
    return VerificationOut(
        ok=report.ok,
        entries=report.entries,
        head_seq=report.head_seq,
        head_hash=report.head_hash,
        first_broken_seq=report.first_broken_seq,
        problem=report.problem,
    )


@router.get(
    "/audit/export",
    tags=["audit"],
    summary="Export the chain as JSON lines",
    description="A header, one line per entry and the head. The file can be verified without "
    "the database: `arbiter audit verify --file`, or any RFC 8785 library.",
    response_class=StreamingResponse,
)
async def audit_export(runtime: Runtime, caller: Reader) -> StreamingResponse:
    tenant_id = caller.context.tenant_id

    async def lines() -> AsyncIterator[str]:
        async with runtime.database.session() as session:
            async for line in runtime.audit.export(session, tenant_id):
                yield line + "\n"

    return StreamingResponse(
        lines(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="audit-export.jsonl"'},
    )


@router.get("/audit/fail-mode", tags=["audit"], summary="What happens when auditing fails")
async def get_fail_mode(runtime: Runtime, caller: Reader) -> FailModeOut:
    async with runtime.database.session() as session:
        tenant = await session.get_one(Tenant, caller.context.tenant_id)
    return FailModeOut(mode=tenant_fail_mode(tenant, runtime.settings.audit.fail_mode))


@router.put(
    "/audit/fail-mode",
    tags=["audit"],
    summary="Set what happens to a request whose audit entry cannot be written",
    description="`closed` fails the request, `open` lets it through. The change is audited.",
)
async def put_fail_mode(body: FailModeIn, runtime: Runtime, caller: Admin) -> FailModeOut:
    async with runtime.database.transaction() as session:
        tenant = await session.get_one(Tenant, caller.context.tenant_id)
        await set_tenant_fail_mode(
            session, runtime.audit, tenant, body.mode, actor_id=caller.context.principal_id
        )
    return FailModeOut(mode=body.mode)
