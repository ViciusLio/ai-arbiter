from decimal import Decimal

import pytest

from ai_arbiter.adapters.local.secrets import EnvSecretStore
from ai_arbiter.core.errors import ConfigurationError, PluginError
from ai_arbiter.core.plugins import PluginRegistry
from ai_arbiter.core.rules import DecisionKind
from ai_arbiter.gateway.llm_router.deployments import Target, build_targets
from ai_arbiter.gateway.llm_router.router import NoRouteError, UpstreamError
from tests.support import chat_request, collect, deployment, mock_router, stream_text


def names(targets: tuple[Target, ...]) -> list[str]:
    return [target.name for target in targets]


def test_models_lists_every_served_name_once() -> None:
    router, _, _ = mock_router(
        [
            deployment("a", serves=("gpt-test", "gpt-other")),
            deployment("b"),
            deployment("c", serves=()),
        ]
    )

    assert router.models() == ["c-model", "gpt-other", "gpt-test"]


def test_priority_strategy_orders_by_priority_then_name() -> None:
    router, _, _ = mock_router(
        [
            deployment("slow", priority=50),
            deployment("b", priority=10),
            deployment("a", priority=10),
        ]
    )

    plan = router.plan("gpt-test")

    assert names(plan.targets) == ["a", "b", "slow"]
    assert [candidate.reason for candidate in plan.candidates] == [
        "priority 10",
        "priority 10",
        "priority 50",
    ]


def test_cost_strategy_orders_by_cost_and_puts_unpriced_deployments_last() -> None:
    costs = {"cheap": Decimal("0.5"), "dear": Decimal("9")}
    router, _, _ = mock_router(
        [deployment("dear", priority=1), deployment("unknown", priority=1), deployment("cheap")],
        strategy="cost",
        cost_of=lambda target: costs.get(target.name),
    )

    plan = router.plan("gpt-test")

    assert names(plan.targets) == ["cheap", "dear", "unknown"]
    assert plan.candidates[0].reason == "cost 0.5 per million tokens"
    assert plan.candidates[2].reason == "no price: placed after priced ones"


def test_cost_strategy_without_prices_falls_back_to_priority() -> None:
    router, _, _ = mock_router(
        [deployment("b", priority=2), deployment("a", priority=1)], strategy="cost"
    )

    assert names(router.plan("gpt-test").targets) == ["a", "b"]


def test_only_deployments_that_serve_the_model_are_candidates() -> None:
    router, _, _ = mock_router([deployment("a"), deployment("b", serves=("other",))])

    assert names(router.plan("gpt-test").targets) == ["a"]
    assert router.plan("unknown-model").candidates == ()


def test_the_plan_is_cut_at_the_attempt_limit_and_says_so() -> None:
    router, _, _ = mock_router(
        [deployment(name, priority=index) for index, name in enumerate("abcd")], max_attempts=2
    )

    plan = router.plan("gpt-test")

    assert names(plan.targets) == ["a", "b"]
    assert [(c.target.name, c.selected, c.reason) for c in plan.candidates[2:]] == [
        ("c", False, "beyond the limit of 2"),
        ("d", False, "beyond the limit of 2"),
    ]


def test_candidates_can_be_excluded_by_policy() -> None:
    router, _, _ = mock_router([deployment("a", priority=1), deployment("b", priority=2)])

    plan = router.plan("gpt-test", allowed={"b"})

    assert names(plan.targets) == ["b"]
    assert plan.candidates[0].reason == "excluded by policy"


async def test_the_first_target_answers_when_it_can() -> None:
    router, _, mock = mock_router([deployment("a", priority=1), deployment("b", priority=2)])

    response, outcome = await router.complete(router.plan("gpt-test"), chat_request())

    assert response.body["model"] == "a-model"
    assert outcome.target is not None
    assert outcome.target.name == "a"
    assert mock.calls("b") == 0


async def test_a_failing_target_is_retried_and_then_the_next_one_is_tried() -> None:
    router, _, mock = mock_router(
        [
            deployment("a", priority=1, settings={"fail": "retryable"}),
            deployment("b", priority=2),
        ],
        retries=1,
    )

    response, outcome = await router.complete(router.plan("gpt-test"), chat_request())

    assert response.body["model"] == "b-model"
    assert [(a.deployment, a.outcome, a.status) for a in outcome.attempts] == [
        ("a", "error", 503),
        ("a", "error", 503),
        ("b", "ok", None),
    ]
    assert mock.calls("a") == 2


async def test_a_retry_on_the_same_target_can_succeed() -> None:
    router, _, _ = mock_router(
        [
            deployment("a", settings={"fail": "retryable", "fail_first": 1}),
            deployment("b", priority=200),
        ],
        retries=1,
    )

    _, outcome = await router.complete(router.plan("gpt-test"), chat_request())

    assert [(a.deployment, a.outcome) for a in outcome.attempts] == [("a", "error"), ("a", "ok")]


async def test_a_request_the_provider_rejects_is_not_sent_elsewhere() -> None:
    router, _, mock = mock_router(
        [deployment("a", priority=1, settings={"fail": "fatal"}), deployment("b", priority=2)]
    )

    with pytest.raises(UpstreamError) as raised:
        await router.complete(router.plan("gpt-test"), chat_request())

    assert mock.calls("b") == 0
    assert raised.value.decision.outcome == "failed"


async def test_when_every_target_fails_the_decision_lists_every_attempt() -> None:
    router, _, _ = mock_router(
        [
            deployment("a", priority=1, settings={"fail": "retryable"}),
            deployment("b", priority=2, settings={"fail": "retryable"}),
        ],
        retries=0,
    )

    with pytest.raises(UpstreamError) as raised:
        await router.complete(router.plan("gpt-test"), chat_request())

    decision = raised.value.decision
    assert decision.kind is DecisionKind.ROUTING
    assert decision.outcome == "failed"
    assert decision.details["attempts"] == [
        {"deployment": "a", "outcome": "error", "error": "ProviderError", "status": 503},
        {"deployment": "b", "outcome": "error", "error": "ProviderError", "status": 503},
    ]


async def test_no_deployment_for_the_model_is_its_own_error() -> None:
    router, _, _ = mock_router([deployment("a")])

    with pytest.raises(NoRouteError, match="no deployment serves the model 'missing'"):
        await router.complete(router.plan("missing"), chat_request(model="missing"))


async def test_the_routing_decision_explains_candidates_and_result() -> None:
    router, _, _ = mock_router(
        [deployment("a", priority=1, region="westeurope"), deployment("b", priority=2)],
        max_attempts=1,
    )

    _, outcome = await router.complete(router.plan("gpt-test"), chat_request())
    decision = outcome.decision()

    assert decision.outcome == "route:a"
    assert decision.details["strategy"] == "priority"
    assert decision.details["candidates"] == [
        {
            "deployment": "a",
            "provider": "mock",
            "model": "a-model",
            "region": "westeurope",
            "selected": True,
            "reason": "priority 1",
        },
        {
            "deployment": "b",
            "provider": "mock",
            "model": "b-model",
            "region": None,
            "selected": False,
            "reason": "beyond the limit of 1",
        },
    ]
    assert decision.audit_payload()["details"] == decision.details


async def test_a_stream_falls_back_before_the_first_chunk() -> None:
    router, _, _ = mock_router(
        [
            deployment("a", priority=1, settings={"fail": "retryable"}),
            deployment("b", priority=2, settings={"reply": "from b"}),
        ],
        retries=0,
    )

    chunks, outcome = await router.open_stream(router.plan("gpt-test"), chat_request(stream=True))

    assert outcome.target is not None
    assert outcome.target.name == "b"
    assert stream_text(await collect(chunks)) == "from b"


async def test_a_stream_that_cannot_start_anywhere_is_an_upstream_error() -> None:
    router, _, _ = mock_router([deployment("a", settings={"fail": "retryable"})], retries=0)

    with pytest.raises(UpstreamError):
        await router.open_stream(router.plan("gpt-test"), chat_request(stream=True))


def test_an_unknown_provider_plugin_is_an_error_at_startup() -> None:
    with pytest.raises(PluginError, match="unknown plugin 'nope' for 'llm_providers'"):
        build_targets([deployment("a", provider="nope")], PluginRegistry(), EnvSecretStore({}))


def test_settings_the_plugin_rejects_are_an_error_at_startup() -> None:
    with pytest.raises(
        ConfigurationError,
        match="deployment 'a': invalid settings for provider 'mock': unknown_option",
    ):
        build_targets(
            [deployment("a", settings={"unknown_option": 1})], PluginRegistry(), EnvSecretStore({})
        )


def test_deployments_of_one_plugin_share_its_instance() -> None:
    targets, providers = build_targets(
        [deployment("a"), deployment("b")], PluginRegistry(), EnvSecretStore({})
    )

    assert [target.name for target in targets] == ["a", "b"]
    assert list(providers) == ["mock"]
