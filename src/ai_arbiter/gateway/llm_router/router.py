"""Route planning and execution with fallback and retry.

A plan is an ordered list of deployments for one requested model, together with the
reason each candidate is where it is. The plan and what happened to each attempt become
a ``Decision`` of kind ``routing``, which is audited.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from ai_arbiter.core.canonical_json import sha256_hex
from ai_arbiter.core.config.settings import RouterSettings
from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.ports import LLMProvider
from ai_arbiter.core.ports.llm import ChatChunk, ChatRequest, ChatResponse, ProviderError
from ai_arbiter.core.rules.decision import Decision, DecisionKind
from ai_arbiter.gateway.llm_router.deployments import Target

# Comparable cost of a deployment, or ``None`` when it has no price.
CostOf = Callable[[Target], Decimal | None]


class NoRouteError(ArbiterError):
    """No configured deployment serves the requested model."""


class UpstreamError(ArbiterError):
    """Every deployment that was tried failed."""

    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        super().__init__("no model provider could complete the request")


@dataclass(frozen=True)
class Candidate:
    target: Target
    selected: bool
    reason: str


@dataclass(frozen=True)
class Attempt:
    deployment: str
    outcome: Literal["ok", "error"]
    error: str | None = None  # exception class name, never a message
    status: int | None = None


@dataclass(frozen=True)
class RoutePlan:
    requested_model: str
    strategy: str
    candidates: tuple[Candidate, ...]

    @property
    def targets(self) -> tuple[Target, ...]:
        return tuple(candidate.target for candidate in self.candidates if candidate.selected)


@dataclass
class RouteOutcome:
    plan: RoutePlan
    attempts: list[Attempt] = field(default_factory=list)
    target: Target | None = None

    def decision(self) -> Decision:
        """The audited record of this routing: candidates, reasons, attempts, result."""
        candidates = [
            {
                "deployment": candidate.target.name,
                "provider": candidate.target.deployment.provider,
                "model": candidate.target.deployment.model,
                "region": candidate.target.deployment.region,
                "selected": candidate.selected,
                "reason": candidate.reason,
            }
            for candidate in self.plan.candidates
        ]
        attempts = [
            {
                "deployment": attempt.deployment,
                "outcome": attempt.outcome,
                "error": attempt.error,
                "status": attempt.status,
            }
            for attempt in self.attempts
        ]
        if self.target is not None:
            outcome = f"route:{self.target.name}"
        elif not self.plan.targets:
            outcome = "no_route"
        else:
            outcome = "failed"
        return Decision(
            kind=DecisionKind.ROUTING,
            outcome=outcome,
            input_digest=sha256_hex(
                {"model": self.plan.requested_model, "strategy": self.plan.strategy}
            ),
            details={
                "requested_model": self.plan.requested_model,
                "strategy": self.plan.strategy,
                "candidates": candidates,
                "attempts": attempts,
            },
        )


class Router:
    def __init__(
        self,
        targets: Sequence[Target],
        providers: Mapping[str, LLMProvider],
        settings: RouterSettings,
        *,
        cost_of: CostOf | None = None,
    ) -> None:
        self._targets = list(targets)
        self._providers = providers
        self._settings = settings
        self._cost_of = cost_of

    def models(self) -> list[str]:
        """Every model name clients may ask for, sorted."""
        return sorted({model for target in self._targets for model in target.config.served_models})

    def allowed_for(self, tier: str) -> tuple[frozenset[str] | None, str]:
        """Deployment names a system of this risk tier may use, and how to say why not.

        ``None`` means no constraint is configured for the tier.
        """
        constraint = self._settings.constraints.get(tier)  # type: ignore[call-overload]
        if constraint is None:
            return None, ""
        names = frozenset(
            target.name
            for target in self._targets
            if (
                constraint.allowed_deployments is None
                or target.name in constraint.allowed_deployments
            )
            and (
                constraint.allowed_regions is None
                or target.deployment.region in constraint.allowed_regions
            )
        )
        return names, f"not allowed for the risk tier {tier}"

    def plan(
        self,
        model: str,
        *,
        allowed: Collection[str] | None = None,
        exclusion_reason: str = "excluded by policy",
    ) -> RoutePlan:
        """Order the deployments that serve ``model``.

        ``allowed``, when given, restricts the plan to those deployment names; the others
        stay in the plan as excluded candidates, with the reason.
        """
        serving = [target for target in self._targets if model in target.config.served_models]
        ordered, reasons = self._order(serving)
        candidates: list[Candidate] = []
        kept = 0
        for target in ordered:
            if allowed is not None and target.name not in allowed:
                candidates.append(Candidate(target, False, exclusion_reason))
            elif kept >= self._settings.max_attempts:
                candidates.append(
                    Candidate(target, False, f"beyond the limit of {self._settings.max_attempts}")
                )
            else:
                kept += 1
                candidates.append(Candidate(target, True, reasons[target.name]))
        return RoutePlan(
            requested_model=model, strategy=self._settings.strategy, candidates=tuple(candidates)
        )

    def _order(self, targets: list[Target]) -> tuple[list[Target], dict[str, str]]:
        by_priority = sorted(targets, key=lambda target: (target.config.priority, target.name))
        if self._settings.strategy == "priority" or self._cost_of is None:
            return by_priority, {
                target.name: f"priority {target.config.priority}" for target in by_priority
            }
        costs = {target.name: self._cost_of(target) for target in by_priority}
        priced = sorted(
            (target for target in by_priority if costs[target.name] is not None),
            key=lambda target: (costs[target.name], target.config.priority, target.name),
        )
        unpriced = [target for target in by_priority if costs[target.name] is None]
        reasons = {
            target.name: f"cost {costs[target.name]} per million tokens" for target in priced
        }
        reasons.update({target.name: "no price: placed after priced ones" for target in unpriced})
        return priced + unpriced, reasons

    async def _attempts(
        self, plan: RoutePlan, outcome: RouteOutcome, call: Callable[[Target], Any]
    ) -> Any:
        """Try each target in order, each up to ``1 + retries`` times."""
        if not plan.targets:
            if plan.candidates:
                reasons = sorted({candidate.reason for candidate in plan.candidates})
                raise NoRouteError(
                    f"no deployment may serve the model '{plan.requested_model}' for this "
                    f"request: {'; '.join(reasons)}"
                )
            raise NoRouteError(f"no deployment serves the model '{plan.requested_model}'")
        for target in plan.targets:
            for attempt in range(1 + self._settings.retries):
                try:
                    result = await call(target)
                except ProviderError as error:
                    outcome.attempts.append(
                        Attempt(target.name, "error", type(error).__name__, error.status)
                    )
                    if not error.retryable:
                        raise UpstreamError(outcome.decision()) from error
                    if attempt < self._settings.retries and self._settings.retry_backoff_ms:
                        await asyncio.sleep(self._settings.retry_backoff_ms * (attempt + 1) / 1000)
                    continue
                outcome.attempts.append(Attempt(target.name, "ok"))
                outcome.target = target
                return result
        raise UpstreamError(outcome.decision())

    async def complete(
        self, plan: RoutePlan, request: ChatRequest
    ) -> tuple[ChatResponse, RouteOutcome]:
        """Call the planned deployments until one answers.

        Raises ``NoRouteError`` for an empty plan and ``UpstreamError`` when every attempt
        failed or the provider refused the request itself.
        """
        outcome = RouteOutcome(plan)

        async def call(target: Target) -> ChatResponse:
            return await self._providers[target.deployment.provider].chat(
                request, target.deployment
            )

        response: ChatResponse = await self._attempts(plan, outcome, call)
        return response, outcome

    async def open_stream(
        self, plan: RoutePlan, request: ChatRequest
    ) -> tuple[AsyncIterator[ChatChunk], RouteOutcome]:
        """Start a stream on the first deployment that accepts the request.

        Fallback and retry happen only until the first chunk arrives; after that the
        client is already receiving this deployment's answer.
        """
        outcome = RouteOutcome(plan)

        async def call(target: Target) -> tuple[ChatChunk | None, AsyncIterator[ChatChunk]]:
            iterator = (
                self._providers[target.deployment.provider]
                .stream(request, target.deployment)
                .__aiter__()
            )
            try:
                return await anext(iterator), iterator
            except StopAsyncIteration:
                return None, iterator

        first, rest = await self._attempts(plan, outcome, call)

        async def chunks() -> AsyncIterator[ChatChunk]:
            if first is not None:
                yield first
                async for chunk in rest:
                    yield chunk

        return chunks(), outcome
