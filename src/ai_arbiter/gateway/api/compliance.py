"""Control plane of the compliance toolkit: inventory, classification, findings, digest.

This module is where the HTTP application composes the gateway with the compliance
toolkit; the two packages do not import each other anywhere else (ADR-0010).
"""

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ai_arbiter.compliance.classifier.model import Classification, ReviewDecision
from ai_arbiter.compliance.classifier.service import EffectiveClassification
from ai_arbiter.compliance.digest.model import build_digest, record_digest_run
from ai_arbiter.compliance.digest.render import render_digest
from ai_arbiter.compliance.findings.model import Finding, FindingStatus, SuppressionScope
from ai_arbiter.compliance.inventory.declarations import SystemDeclaration
from ai_arbiter.compliance.inventory.model import AISystem
from ai_arbiter.compliance.reports.model import build_audit_report, build_system_report
from ai_arbiter.compliance.reports.render import render_audit_report, render_system_report
from ai_arbiter.compliance.runtime import ComplianceRuntime
from ai_arbiter.core.domain.risk import RiskTier
from ai_arbiter.core.errors import ConflictError, PermissionDeniedError
from ai_arbiter.core.i18n import SUPPORTED_LOCALES, Translator, negotiate
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.gateway.api.deps import Admin, Reader, Runtime

router = APIRouter(prefix="/api/v1")

NOTE = (
    "Indicative. Classifications and findings support the judgement of a person and do "
    "not replace it. Arbiter is a support tool and does not provide legal advice."
)


def get_compliance(request: Request) -> ComplianceRuntime:
    compliance: ComplianceRuntime = request.app.state.compliance
    return compliance


Compliance = Annotated[ComplianceRuntime, Depends(get_compliance)]


def _translator(request: Request) -> Translator:
    return Translator(negotiate(request.headers.get("accept-language")))


# --- inventory and classification --------------------------------------------------------


class ObligationOut(BaseModel):
    id: str
    outcome: str
    text: str
    legal_refs: list[str]
    roles: list[str]
    applies_from: date | None
    applicable: bool
    applies_to_declared_roles: bool


class ClassificationOut(BaseModel):
    id: UUID
    tier: RiskTier
    engine_tier: RiskTier
    status: Literal["proposed", "confirmed", "overridden"]
    reviewed_by: UUID | None
    review_reason: str | None
    rulepack: str
    rulepack_version: str
    rulepack_review: str | None
    regulation_as_of: date | None
    obligations: list[ObligationOut]
    missing_facts: list[str]
    created_at: datetime
    note: str = NOTE


class SystemOut(BaseModel):
    id: UUID
    key: str
    name: str
    purpose: str
    lifecycle: str
    origin: str
    roles: list[str]
    facts: dict[str, Any]
    models: list[Any]
    classification: ClassificationOut | None


class QuestionOut(BaseModel):
    fact: str
    question: str
    stage: str | None
    reference: str | None


class ReviewIn(BaseModel):
    decision: ReviewDecision
    tier: RiskTier | None = None
    reason: str = Field(default="", max_length=2000)


def _classification(
    current: EffectiveClassification | None,
    compliance: ComplianceRuntime,
    t: Translator,
    today: date,
) -> ClassificationOut | None:
    if current is None:
        return None
    row: Classification = current.classification
    obligations = []
    for item in row.obligations:
        applies = date.fromisoformat(item["applies_from"]) if item.get("applies_from") else None
        key = item["message_key"]
        obligations.append(
            ObligationOut(
                id=item["id"],
                outcome=item["outcome"],
                text=t.text(key) if t.has(key) else key,
                legal_refs=item.get("legal_refs") or [],
                roles=item.get("roles") or [],
                applies_from=applies,
                applicable=applies is None or applies <= today,
                applies_to_declared_roles=bool(item.get("applies_to_declared_roles")),
            )
        )
    regulation = compliance.ai_act_pack.regulation
    return ClassificationOut(
        id=row.id,
        tier=current.tier,
        engine_tier=RiskTier(row.tier),
        status=current.status,
        reviewed_by=current.review.reviewer_id if current.review else None,
        review_reason=current.review.reason if current.review else None,
        rulepack=row.rulepack,
        rulepack_version=row.rulepack_version,
        rulepack_review=regulation.review if regulation else None,
        regulation_as_of=row.regulation_as_of,
        obligations=obligations,
        missing_facts=list(row.missing_facts),
        created_at=row.created_at,
    )


async def _system_out(
    session: Any, system: AISystem, compliance: ComplianceRuntime, t: Translator
) -> SystemOut:
    roles = await compliance.inventory.roles(session, system)
    current = await compliance.classifier.current(session, system.tenant_id, system.id)
    return SystemOut(
        id=system.id,
        key=system.key,
        name=system.name,
        purpose=system.purpose,
        lifecycle=system.lifecycle,
        origin=system.origin,
        roles=[role.role for role in roles],
        facts=dict(system.attributes or {}),
        models=list(system.models_used or []),
        classification=_classification(current, compliance, t, compliance.clock.now().date()),
    )


@router.get("/systems", tags=["inventory"], summary="List declared AI systems")
async def list_systems(
    request: Request, runtime: Runtime, compliance: Compliance, caller: Reader
) -> list[SystemOut]:
    t = _translator(request)
    async with runtime.database.session() as session:
        systems = await compliance.inventory.list(session, caller.context.tenant_id)
        return [await _system_out(session, system, compliance, t) for system in systems]


@router.put(
    "/systems/{key}",
    tags=["inventory"],
    summary="Declare an AI system, or bring it in line with the declaration",
    description="Idempotent. The system is classified in the same request; the result is "
    "indicative until a person reviews it. A fact that is left out is not answered, which "
    "is different from false.",
)
async def declare_system(
    key: str,
    body: SystemDeclaration,
    request: Request,
    runtime: Runtime,
    compliance: Compliance,
    caller: Admin,
) -> SystemOut:
    if body.key != key:
        raise ConflictError("the key in the body differs from the key in the path")
    if body.use:
        raise ConflictError("'use' refers to fact sets of a file; send the facts themselves")
    async with runtime.database.transaction() as session:
        declared = await compliance.inventory.declare(
            session, caller.context.tenant_id, body, actor_id=caller.context.principal_id
        )
        await compliance.classifier.classify_system(
            session, declared.system, actor_id=caller.context.principal_id
        )
        return await _system_out(session, declared.system, compliance, _translator(request))


@router.get("/systems/{key}", tags=["inventory"], summary="A system with its classification")
async def get_system(
    key: str, request: Request, runtime: Runtime, compliance: Compliance, caller: Reader
) -> SystemOut:
    async with runtime.database.session() as session:
        system = await compliance.inventory.get(session, caller.context.tenant_id, key)
        return await _system_out(session, system, compliance, _translator(request))


@router.get(
    "/systems/{key}/questions",
    tags=["inventory"],
    summary="The questions still to answer for a system",
    description="Facts that could change the classification and were not answered, in "
    "questionnaire order. Details of an area are asked only once the area applies.",
)
async def system_questions(
    key: str, request: Request, runtime: Runtime, compliance: Compliance, caller: Reader
) -> list[QuestionOut]:
    t = _translator(request)
    async with runtime.database.session() as session:
        system = await compliance.inventory.get(session, caller.context.tenant_id, key)
        result = await compliance.classifier.evaluate(session, system)
    pack = compliance.ai_act_pack
    return [
        QuestionOut(
            fact=name,
            question=t.text(f"fact.{name}"),
            stage=pack.facts[name].stage,
            reference=pack.facts[name].ref,
        )
        for name in compliance.classifier.questions(result)
    ]


@router.post(
    "/systems/{key}/review",
    tags=["inventory"],
    summary="Confirm or override the classification of a system",
    description="Recorded under the principal of the API key. Confirming keeps the "
    "indicative tier; overriding sets another one and needs a reason.",
)
async def review_system(
    key: str,
    body: ReviewIn,
    request: Request,
    runtime: Runtime,
    compliance: Compliance,
    caller: Admin,
) -> SystemOut:
    if caller.context.principal_id is None:
        raise PermissionDeniedError("a review needs an API key that belongs to a principal")
    async with runtime.database.transaction() as session:
        system = await compliance.inventory.get(session, caller.context.tenant_id, key)
        await compliance.classifier.review(
            session,
            caller.context.tenant_id,
            system.id,
            decision=body.decision,
            reviewer_id=caller.context.principal_id,
            reason=body.reason,
            tier=body.tier,
        )
        return await _system_out(session, system, compliance, _translator(request))


# --- scans and findings ------------------------------------------------------------------


class ScanOut(BaseModel):
    id: UUID
    rulepack_version: str
    started_at: datetime
    finished_at: datetime | None
    stats: dict[str, int]


class FindingOut(BaseModel):
    id: UUID
    rule_id: str
    severity: str
    status: str
    text: str
    ai_system_id: UUID | None
    legal_refs: list[dict[str, str]]
    applies_from: date | None
    accepted_until: date | None
    first_seen: datetime
    last_seen: datetime
    occurrences: int


class FindingReviewOut(BaseModel):
    from_status: str
    to_status: str
    reviewer_id: UUID | None
    reason: str
    created_at: datetime


class FindingDetailOut(FindingOut):
    evidence: list[dict[str, Any]]
    history: list[FindingReviewOut]
    note: str = NOTE


class TransitionIn(BaseModel):
    to: FindingStatus
    reason: str = Field(default="", max_length=2000)
    accepted_until: date | None = None
    suppress: SuppressionScope | None = None


class SuppressionIn(BaseModel):
    rule_id: str
    scope: SuppressionScope = SuppressionScope.RULE
    scope_ref: str = ""
    reason: str = Field(max_length=2000)
    expires_at: datetime | None = None


class SuppressionOut(BaseModel):
    id: UUID
    rule_id: str
    scope: str
    scope_ref: str
    reason: str
    created_by: UUID | None
    created_at: datetime
    expires_at: datetime | None


def _finding(finding: Finding, t: Translator) -> dict[str, Any]:
    key = finding.message_key
    return {
        "id": finding.id,
        "rule_id": finding.rule_id,
        "severity": finding.severity,
        "status": finding.status,
        "text": t.text(key) if t.has(key) else key,
        "ai_system_id": finding.ai_system_id,
        "legal_refs": list(finding.legal_refs),
        "applies_from": finding.applies_from,
        "accepted_until": finding.accepted_until,
        "first_seen": finding.first_seen,
        "last_seen": finding.last_seen,
        "occurrences": finding.occurrences,
    }


@router.post(
    "/scans",
    tags=["findings"],
    summary="Scan the inventory and the traffic of the last 30 days",
    status_code=status.HTTP_201_CREATED,
)
async def run_scan(runtime: Runtime, compliance: Compliance, caller: Admin) -> ScanOut:
    async with runtime.database.transaction() as session:
        scan = await compliance.scanner.run(
            session, caller.context.tenant_id, actor_id=caller.context.principal_id
        )
    return ScanOut(
        id=scan.id,
        rulepack_version=scan.rulepack_version,
        started_at=scan.started_at,
        finished_at=scan.finished_at,
        stats=dict(scan.stats),
    )


@router.get(
    "/findings",
    tags=["findings"],
    summary="List findings",
    description="Active findings (open and confirmed) unless statuses are named.",
)
async def list_findings(
    request: Request,
    runtime: Runtime,
    compliance: Compliance,
    caller: Reader,
    statuses: Annotated[list[FindingStatus] | None, Query(alias="status")] = None,
) -> list[FindingOut]:
    t = _translator(request)
    wanted = [item.value for item in statuses] if statuses else ["open", "confirmed"]
    async with runtime.database.session() as session:
        findings = await compliance.findings.list(
            session, caller.context.tenant_id, statuses=wanted
        )
    return [FindingOut(**_finding(finding, t)) for finding in findings]


@router.get("/findings/{finding_id}", tags=["findings"], summary="A finding with its evidence")
async def get_finding(
    finding_id: UUID, request: Request, runtime: Runtime, compliance: Compliance, caller: Reader
) -> FindingDetailOut:
    async with runtime.database.session() as session:
        detail = await compliance.findings.get(session, caller.context.tenant_id, finding_id)
    return FindingDetailOut(
        **_finding(detail.finding, _translator(request)),
        evidence=[dict(item.data) for item in detail.evidence],
        history=[
            FindingReviewOut(
                from_status=item.from_status,
                to_status=item.to_status,
                reviewer_id=item.reviewer_id,
                reason=item.reason,
                created_at=item.created_at,
            )
            for item in detail.reviews
        ],
    )


@router.post(
    "/findings/{finding_id}/transitions",
    tags=["findings"],
    summary="Change the status of a finding",
    description="Recorded under the principal of the API key, and audited. Rejecting or "
    "accepting needs a reason; accepting needs an expiry date.",
)
async def transition_finding(
    finding_id: UUID,
    body: TransitionIn,
    request: Request,
    runtime: Runtime,
    compliance: Compliance,
    caller: Admin,
) -> FindingOut:
    if caller.context.principal_id is None:
        raise PermissionDeniedError("a review needs an API key that belongs to a principal")
    async with runtime.database.transaction() as session:
        finding = await compliance.findings.transition(
            session,
            caller.context.tenant_id,
            finding_id,
            body.to,
            reviewer_id=caller.context.principal_id,
            reason=body.reason,
            accepted_until=body.accepted_until,
            suppress=body.suppress,
        )
    return FindingOut(**_finding(finding, _translator(request)))


def _suppression(row: Any) -> SuppressionOut:
    return SuppressionOut(
        id=row.id,
        rule_id=row.rule_id,
        scope=row.scope_type,
        scope_ref=row.scope_ref,
        reason=row.reason,
        created_by=row.created_by,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )


@router.get("/suppressions", tags=["findings"], summary="List suppressions")
async def list_suppressions(
    runtime: Runtime, compliance: Compliance, caller: Reader
) -> list[SuppressionOut]:
    async with runtime.database.session() as session:
        rows = await compliance.findings.suppressions(session, caller.context.tenant_id)
    return [_suppression(row) for row in rows]


@router.post(
    "/suppressions",
    tags=["findings"],
    summary="Stop a scan rule from reporting, for a scope",
    status_code=status.HTTP_201_CREATED,
)
async def create_suppression(
    body: SuppressionIn, runtime: Runtime, compliance: Compliance, caller: Admin
) -> SuppressionOut:
    if body.expires_at is not None and body.expires_at.tzinfo is None:
        raise ConflictError("expires_at must carry a time zone")
    async with runtime.database.transaction() as session:
        row = await compliance.findings.suppress(
            session,
            caller.context.tenant_id,
            rule_id=body.rule_id,
            scope=body.scope,
            scope_ref=body.scope_ref,
            reason=body.reason,
            created_by=caller.context.principal_id,
            expires_at=body.expires_at,
        )
    return _suppression(row)


@router.delete(
    "/suppressions/{suppression_id}",
    tags=["findings"],
    summary="Remove a suppression",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_suppression(
    suppression_id: UUID, runtime: Runtime, compliance: Compliance, caller: Admin
) -> Response:
    async with runtime.database.transaction() as session:
        await compliance.findings.remove_suppression(
            session, caller.context.tenant_id, suppression_id, actor_id=caller.context.principal_id
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- digest ------------------------------------------------------------------------------


@router.post(
    "/digests",
    tags=["digest"],
    summary="Build the digest of the last days",
    description="Inventory by indicative tier, active findings, gateway traffic and the head "
    "of the audit chain, as Markdown or HTML, in English or Italian.",
    response_class=PlainTextResponse,
)
async def build_digest_now(
    runtime: Runtime,
    compliance: Compliance,
    caller: Reader,
    locale: Annotated[str, Query()] = "en",
    output: Annotated[Literal["markdown", "html"], Query(alias="format")] = "markdown",
    days: Annotated[int, Query(ge=1, le=92)] = 1,
) -> PlainTextResponse:
    if locale not in SUPPORTED_LOCALES:
        raise ConflictError(f"unsupported locale '{locale}'")
    now = compliance.clock.now()
    async with runtime.database.transaction() as session:
        tenant = await session.get_one(Tenant, caller.context.tenant_id)
        digest = await build_digest(
            session,
            tenant,
            classifier=compliance.classifier,
            findings=compliance.findings,
            period_start=now - timedelta(days=days),
            period_end=now,
            generated_at=now,
        )
        await record_digest_run(session, tenant, digest, [locale])
    media = "text/html" if output == "html" else "text/markdown"
    return PlainTextResponse(
        render_digest(digest, locale=locale, output=output), media_type=f"{media}; charset=utf-8"
    )


# --- reports -----------------------------------------------------------------------------

Output = Annotated[Literal["markdown", "html"], Query(alias="format")]


def _document(text: str, output: str) -> PlainTextResponse:
    media = "text/html" if output == "html" else "text/markdown"
    return PlainTextResponse(text, media_type=f"{media}; charset=utf-8")


def _locale(locale: str) -> str:
    if locale not in SUPPORTED_LOCALES:
        raise ConflictError(f"unsupported locale '{locale}'")
    return locale


@router.get(
    "/systems/{key}/report",
    tags=["reports"],
    summary="Everything recorded about one system",
    description="Declaration, indicative classification with its obligations and dates, "
    "review, findings and traffic of the last 30 days, as Markdown or HTML.",
    response_class=PlainTextResponse,
)
async def system_report(
    key: str,
    runtime: Runtime,
    compliance: Compliance,
    caller: Reader,
    locale: Annotated[str, Query()] = "en",
    output: Output = "markdown",
) -> PlainTextResponse:
    locale = _locale(locale)
    async with runtime.database.session() as session:
        tenant = await session.get_one(Tenant, caller.context.tenant_id)
        report = await build_system_report(session, tenant, compliance, key)
    return _document(render_system_report(report, locale=locale, output=output), output)


@router.get(
    "/audit/report",
    tags=["reports"],
    summary="The audit log over a period",
    description="Whether the whole chain verifies, and the entries of the last days, as "
    "Markdown or HTML. The chain is recomputed from its first entry.",
    response_class=PlainTextResponse,
)
async def audit_report(
    runtime: Runtime,
    compliance: Compliance,
    caller: Reader,
    locale: Annotated[str, Query()] = "en",
    output: Output = "markdown",
    days: Annotated[int, Query(ge=1, le=366)] = 30,
) -> PlainTextResponse:
    locale = _locale(locale)
    now = compliance.clock.now()
    async with runtime.database.session() as session:
        tenant = await session.get_one(Tenant, caller.context.tenant_id)
        report = await build_audit_report(
            session,
            tenant,
            runtime.audit,
            period_start=now - timedelta(days=days),
            period_end=now,
            generated_at=now,
        )
    return _document(render_audit_report(report, locale=locale, output=output), output)
