"""The path of a chat completion through the gateway.

    budgets and PII detection -> policy -> routing -> provider -> one transaction with
    the interaction, the audit entries and the outbox event

No database transaction is open while a provider is being called. Prompt and completion
text is never stored and never logged.
"""

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from ai_arbiter.core.audit import AuditRecord, DatabaseAuditLog, FailMode, tenant_fail_mode
from ai_arbiter.core.config.settings import PolicySettings, RedactionSettings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.tenancy import TenantContext
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.interaction import Interaction, InteractionRecorded, InteractionStatus
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.core.ports import EventBus, PIIDetector, PolicyEngine
from ai_arbiter.core.ports.llm import ChatChunk, ChatRequest, ProviderError, Usage
from ai_arbiter.core.redaction import (
    RedactionStrategy,
    categories,
    derive_key,
    keyed_digest,
    redact,
)
from ai_arbiter.core.rules import Decision
from ai_arbiter.gateway.finops.budgets import BudgetService, BudgetStatus
from ai_arbiter.gateway.finops.metering import UsageMeter, estimate_usage
from ai_arbiter.gateway.llm_router.deployments import Target
from ai_arbiter.gateway.llm_router.router import NoRouteError, RouteOutcome, Router, UpstreamError
from ai_arbiter.gateway.policy.engine import PolicyOutcome, collect_facts

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")


class PolicyDeniedError(ArbiterError):
    """Policy stopped the request before any provider was called."""

    def __init__(self, decision: Decision, interaction_id: UUID) -> None:
        self.decision = decision
        self.interaction_id = interaction_id
        super().__init__("the request was denied by policy")


class AuditUnavailableError(ArbiterError):
    """The audit entry could not be written and the tenant's fail mode is ``closed``."""

    def __init__(self) -> None:
        super().__init__("the request could not be recorded in the audit log")


@dataclass
class ChatResult:
    interaction_id: UUID
    decision: Decision
    budget: BudgetStatus
    pii_categories: list[str]
    body: Mapping[str, Any] | None = None
    chunks: AsyncIterator[ChatChunk] | None = None


@dataclass
class _Prepared:
    """What is known about a request before a provider is called."""

    context: TenantContext
    request: ChatRequest  # as it will be sent: redacted if policy said so
    interaction_id: UUID
    started_at: datetime
    clock_start: float
    decision: Decision
    budget: BudgetStatus
    fail_mode: FailMode
    pii_categories: list[str]
    fingerprint: str | None
    prompt_characters: int
    include_usage: bool = False
    decisions: list[tuple[str, Decision]] = field(default_factory=list)


class ChatService:
    def __init__(
        self,
        *,
        database: Database,
        router: Router,
        meter: UsageMeter,
        budgets: BudgetService,
        policy: PolicyEngine,
        policy_settings: PolicySettings,
        detector: PIIDetector,
        redaction: RedactionSettings,
        redaction_key: bytes | None,
        audit: DatabaseAuditLog,
        bus: EventBus,
        default_fail_mode: FailMode = "closed",
        clock: Clock | None = None,
    ) -> None:
        self._database = database
        self._router = router
        self._meter = meter
        self._budgets = budgets
        self._policy = policy
        self._policy_settings = policy_settings
        self._detector = detector
        self._redaction = redaction
        self._redaction_key = redaction_key
        self._audit = audit
        self._bus = bus
        self._default_fail_mode: FailMode = default_fail_mode
        self._clock = clock if clock is not None else SystemClock()
        self._pending: set[asyncio.Future[bool]] = set()

    # Before the provider

    def _tenant_key(self, purpose: str, tenant_id: UUID) -> bytes | None:
        if self._redaction_key is None:
            return None
        return derive_key(self._redaction_key, purpose, str(tenant_id))

    def _redact_text(self, text: str, tenant_id: UUID) -> str:
        return redact(
            text,
            self._detector.detect(text),
            strategies={
                category: RedactionStrategy(strategy)
                for category, strategy in self._redaction.strategies.items()
            },
            default=RedactionStrategy(self._redaction.default_strategy),
            key=self._tenant_key("redaction", tenant_id),
        )

    def _redact_request(self, request: ChatRequest, tenant_id: UUID) -> ChatRequest:
        messages: list[Mapping[str, Any]] = []
        for message in request.messages:
            content = message.get("content")
            if isinstance(content, str):
                messages.append({**message, "content": self._redact_text(content, tenant_id)})
            elif isinstance(content, list):
                parts = [
                    {**part, "text": self._redact_text(part["text"], tenant_id)}
                    if isinstance(part, Mapping) and isinstance(part.get("text"), str)
                    else part
                    for part in content
                ]
                messages.append({**message, "content": parts})
            else:
                messages.append(message)
        return request.model_copy(update={"messages": tuple(messages)})

    async def _prepare(self, context: TenantContext, request: ChatRequest) -> _Prepared:
        started_at, clock_start = self._clock.now(), time.perf_counter()
        async with self._database.session() as session:
            tenant = await session.get_one(Tenant, context.tenant_id)
            fail_mode = tenant_fail_mode(tenant, self._default_fail_mode)
            budget = await self._budgets.status(session, context)

        found = categories(
            [span for text in request.texts() for span in self._detector.detect(text)]
        )
        facts = collect_facts(
            request,
            allowed_models=self._policy_settings.allowed_models,
            budget=budget,
            pii_categories=found,
            system_declared=context.ai_system_id is not None,
        )
        decision = await self._policy.evaluate("pre_call", facts)
        if decision.outcome == PolicyOutcome.REDACT.value:
            request = self._redact_request(request, context.tenant_id)

        texts = request.texts()
        fingerprint_key = self._tenant_key("fingerprint", context.tenant_id)
        fingerprint = (
            keyed_digest(fingerprint_key, _WHITESPACE.sub(" ", "\n".join(texts)).strip().casefold())
            if fingerprint_key is not None
            else None
        )
        options = request.params.get("stream_options")
        return _Prepared(
            context=context,
            request=request,
            interaction_id=new_id(),
            started_at=started_at,
            clock_start=clock_start,
            decision=decision,
            budget=budget,
            fail_mode=fail_mode,
            pii_categories=found,
            fingerprint=fingerprint,
            prompt_characters=sum(len(text) for text in texts),
            include_usage=isinstance(options, Mapping) and bool(options.get("include_usage")),
            decisions=[("chat.policy", decision)],
        )

    # Recording

    def _interaction(
        self,
        prepared: _Prepared,
        status: InteractionStatus,
        *,
        target: Target | None = None,
        usage: Usage | None = None,
    ) -> Interaction:
        cost = self._meter.cost(target, usage) if target is not None else None
        return Interaction(
            id=prepared.interaction_id,
            tenant_id=prepared.context.tenant_id,
            team_id=prepared.context.team_id,
            project_id=prepared.context.project_id,
            principal_id=prepared.context.principal_id,
            ai_system_id=prepared.context.ai_system_id,
            source_record_id=str(prepared.interaction_id),
            started_at=prepared.started_at,
            duration_ms=int((time.perf_counter() - prepared.clock_start) * 1000),
            requested_model=prepared.request.model,
            deployment=target.name if target else None,
            provider=target.deployment.provider if target else None,
            model=target.deployment.model if target else None,
            region=target.deployment.region if target else None,
            status=status.value,
            streamed=prepared.request.stream,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cached_input_tokens=usage.cached_input_tokens if usage else None,
            usage_estimated=bool(usage and usage.estimated),
            cost_estimate=cost,
            currency=self._meter.catalogue.currency if cost is not None else None,
            price_version=self._meter.catalogue.version if cost is not None else None,
            policy_outcome=prepared.decision.outcome,
            prompt_fingerprint=prepared.fingerprint,
            pii_categories=list(prepared.pii_categories),
            decision_id=prepared.decision.id,
        )

    async def _record(self, prepared: _Prepared, interaction: Interaction) -> bool:
        """Write the interaction, its audit entries and its event in one transaction.

        Returns whether it was written. A failure is logged with the exception class
        only; whether it also fails the request is the caller's decision.
        """
        try:
            async with self._database.transaction() as session:
                await self._meter.record(session, interaction)
                for action, decision in prepared.decisions:
                    await self._audit.append(
                        session,
                        interaction.tenant_id,
                        AuditRecord.of_decision(
                            decision,
                            action=action,
                            actor_id=interaction.principal_id,
                            resource_type="interaction",
                            resource_id=str(interaction.id),
                        ),
                    )
                await self._bus.publish(
                    InteractionRecorded(
                        tenant_id=interaction.tenant_id, interaction_id=interaction.id
                    ),
                    session=session,
                )
        except (SQLAlchemyError, OSError) as error:
            logger.error(
                "interaction could not be recorded",
                extra={"interaction_id": str(interaction.id), "error": type(error).__name__},
            )
            return False
        return True

    async def _record_or_fail(self, prepared: _Prepared, interaction: Interaction) -> None:
        if not await self._record(prepared, interaction) and prepared.fail_mode == "closed":
            raise AuditUnavailableError

    def _usage_or_estimate(
        self, prepared: _Prepared, target: Target, usage: Usage | None, completion_characters: int
    ) -> Usage | None:
        if usage is not None and usage.known:
            return usage
        if target.config.usage_fallback == "estimate":
            return estimate_usage(
                prepared.prompt_characters, completion_characters, target.config.chars_per_token
            )
        return None

    # The two entry points

    async def _start(self, context: TenantContext, request: ChatRequest) -> _Prepared:
        prepared = await self._prepare(context, request)
        if prepared.decision.outcome == PolicyOutcome.DENY.value:
            await self._record_or_fail(
                prepared, self._interaction(prepared, InteractionStatus.DENIED)
            )
            raise PolicyDeniedError(prepared.decision, prepared.interaction_id)
        return prepared

    async def _failed(self, prepared: _Prepared, routing: Decision) -> None:
        prepared.decisions.append(("chat.routing", routing))
        await self._record(prepared, self._interaction(prepared, InteractionStatus.ERROR))

    async def complete(self, context: TenantContext, request: ChatRequest) -> ChatResult:
        """Handle a request that is not streamed.

        Raises ``PolicyDeniedError``, ``NoRouteError``, ``UpstreamError`` or
        ``AuditUnavailableError``.
        """
        prepared = await self._start(context, request)
        plan = self._router.plan(prepared.request.model)
        try:
            response, outcome = await self._router.complete(plan, prepared.request)
        except NoRouteError:
            await self._failed(prepared, RouteOutcome(plan).decision())
            raise
        except UpstreamError as error:
            await self._failed(prepared, error.decision)
            raise

        target = outcome.target
        assert target is not None  # noqa: S101 - set whenever complete() returns
        completion_characters = sum(
            len(choice["message"]["content"])
            for choice in response.body.get("choices", [])
            if isinstance(choice, Mapping)
            and isinstance(choice.get("message"), Mapping)
            and isinstance(choice["message"].get("content"), str)
        )
        usage = self._usage_or_estimate(prepared, target, response.usage, completion_characters)
        prepared.decisions.append(("chat.routing", outcome.decision()))
        await self._record_or_fail(
            prepared, self._interaction(prepared, InteractionStatus.OK, target=target, usage=usage)
        )
        return ChatResult(
            interaction_id=prepared.interaction_id,
            decision=prepared.decision,
            budget=prepared.budget,
            pii_categories=prepared.pii_categories,
            body=response.body,
        )

    async def stream(self, context: TenantContext, request: ChatRequest) -> ChatResult:
        """Handle a streamed request.

        Policy, routing and the choice of deployment happen before this returns, so the
        same errors as ``complete`` are raised here, before the first byte is sent. The
        interaction is recorded when the stream ends or is abandoned.
        """
        prepared = await self._start(context, request)
        plan = self._router.plan(prepared.request.model)
        try:
            chunks, outcome = await self._router.open_stream(plan, prepared.request)
        except NoRouteError:
            await self._failed(prepared, RouteOutcome(plan).decision())
            raise
        except UpstreamError as error:
            await self._failed(prepared, error.decision)
            raise
        target = outcome.target
        assert target is not None  # noqa: S101 - set whenever open_stream() returns
        prepared.decisions.append(("chat.routing", outcome.decision()))
        return ChatResult(
            interaction_id=prepared.interaction_id,
            decision=prepared.decision,
            budget=prepared.budget,
            pii_categories=prepared.pii_categories,
            chunks=self._relay(prepared, target, chunks),
        )

    async def _relay(
        self, prepared: _Prepared, target: Target, chunks: AsyncIterator[ChatChunk]
    ) -> AsyncIterator[ChatChunk]:
        usage: Usage | None = None
        completion_characters = 0
        status = InteractionStatus.ABORTED
        try:
            async for chunk in chunks:
                if chunk.usage is not None:
                    usage = chunk.usage
                for choice in chunk.data.get("choices") or []:
                    delta = choice.get("delta") if isinstance(choice, Mapping) else None
                    if isinstance(delta, Mapping) and isinstance(delta.get("content"), str):
                        completion_characters += len(delta["content"])
                # The gateway asked for usage on its own account; a client that did not
                # ask for it does not get the extra chunk.
                if chunk.usage_only and not prepared.include_usage:
                    continue
                yield chunk
            status = InteractionStatus.OK
        except ProviderError:
            status = InteractionStatus.ERROR
            raise
        finally:
            final = self._usage_or_estimate(prepared, target, usage, completion_characters)
            interaction = self._interaction(prepared, status, target=target, usage=final)
            # The client may be gone and this task cancelled: finish the write anyway.
            task: asyncio.Future[bool] = asyncio.ensure_future(self._record(prepared, interaction))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
            await asyncio.shield(task)

    async def drain(self) -> None:
        """Wait for records still being written. Called when the process stops."""
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)
