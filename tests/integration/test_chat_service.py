from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from ai_arbiter.core.audit import AuditEntry, set_tenant_fail_mode
from ai_arbiter.core.config import load_settings
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.tenancy import TenantContext
from ai_arbiter.core.events.model import OutboxEvent
from ai_arbiter.core.interaction import Interaction
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.core.ports.llm import ChatChunk, ChatRequest, ProviderError
from ai_arbiter.gateway.chat import AuditUnavailableError, PolicyDeniedError
from ai_arbiter.gateway.finops.budgets import BudgetPeriod
from ai_arbiter.gateway.finops.model import UsageRollup
from ai_arbiter.gateway.identity.model import ScopeType
from ai_arbiter.gateway.llm_router.router import NoRouteError, UpstreamError
from ai_arbiter.gateway.runtime import GatewayRuntime, build_runtime
from tests.conftest import TEST_PEPPER
from tests.support import chat_request, collect, stream_text, text_in_database

EMAIL = "mario.rossi@example.com"
MOCK = {"name": "mock", "provider": "mock", "model": "mock-small", "serves": ["gpt-test"]}
ECHO = {**MOCK, "settings": {"echo": True}}

RuntimeFactory = Callable[..., Any]


@pytest.fixture
async def make_runtime(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[RuntimeFactory]:
    monkeypatch.setenv("ARBITER_SECRET_API_KEY_PEPPER", TEST_PEPPER)
    monkeypatch.setenv("ARBITER_SECRET_REDACTION_KEY", "redaction-root-key-for-tests-only")
    built: list[GatewayRuntime] = []

    async def factory(*deployments: dict[str, Any], **settings: Any) -> GatewayRuntime:
        values: dict[str, Any] = {
            "deployments": list(deployments or (MOCK,)),
            "redaction": {"key": "secret://redaction-key"},
            "router": {"retry_backoff_ms": 0, "retries": 0},
            **settings,
        }
        runtime = await build_runtime(load_settings(**values), database)
        built.append(runtime)
        return runtime

    yield factory
    for runtime in built:
        await runtime.aclose()


@pytest.fixture
def context(tenant_id: UUID) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id, team_id=new_id(), project_id=new_id(), principal_id=new_id()
    )


async def rows(database: Database, model: Any) -> list[Any]:
    async with database.session() as session:
        return list((await session.scalars(select(model))).all())


async def audit_entries(database: Database) -> list[AuditEntry]:
    async with database.session() as session:
        return list((await session.scalars(select(AuditEntry).order_by(AuditEntry.seq))).all())


async def test_an_allowed_request_is_answered_metered_and_audited(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime()

    result = await runtime.chat.complete(context, chat_request("x" * 400))

    assert result.body is not None
    assert result.body["choices"][0]["message"]["role"] == "assistant"
    assert result.decision.outcome == "allow"
    interaction = (await rows(database, Interaction))[0]
    assert interaction.id == result.interaction_id
    assert (interaction.status, interaction.streamed) == ("ok", False)
    assert (interaction.requested_model, interaction.deployment) == ("gpt-test", "mock")
    assert (interaction.provider, interaction.model) == ("mock", "mock-small")
    assert (interaction.input_tokens, interaction.output_tokens) == (100, 9)
    assert interaction.usage_estimated is False
    assert interaction.cost_estimate == Decimal("0.0000204")
    assert (interaction.currency, interaction.price_version) == ("USD", runtime.catalogue.version)
    assert interaction.policy_outcome == "allow"
    assert interaction.decision_id == result.decision.id
    assert interaction.project_id == context.project_id
    assert interaction.duration_ms is not None


async def test_each_request_leaves_a_policy_and_a_routing_entry_in_a_sound_chain(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime()

    result = await runtime.chat.complete(context, chat_request())
    await runtime.chat.complete(context, chat_request())

    entries = await audit_entries(database)
    assert [(e.seq, e.action, e.outcome) for e in entries] == [
        (1, "chat.policy", "allow"),
        (2, "chat.routing", "route:mock"),
        (3, "chat.policy", "allow"),
        (4, "chat.routing", "route:mock"),
    ]
    assert entries[0].resource_id == str(result.interaction_id)
    assert entries[0].actor_id == context.principal_id
    assert entries[0].decision is not None
    assert entries[0].decision["details"]["pack"] == "policy"
    async with database.session() as session:
        assert (await runtime.audit.verify(session, context.tenant_id)).ok


async def test_an_event_and_the_roll_ups_are_written_with_the_interaction(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime()

    result = await runtime.chat.complete(context, chat_request())

    events = await rows(database, OutboxEvent)
    assert [(e.type, e.payload["interaction_id"]) for e in events] == [
        ("interaction.recorded", str(result.interaction_id))
    ]
    rollups = await rows(database, UsageRollup)
    assert {r.scope_type for r in rollups} == {"tenant", "team", "project", "principal"}
    assert all(r.requests == 1 for r in rollups)


async def test_personal_data_is_redacted_before_the_prompt_reaches_the_provider(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime(ECHO)

    result = await runtime.chat.complete(context, chat_request(f"Write to {EMAIL} please"))

    assert result.body is not None
    assert result.body["choices"][0]["message"]["content"] == "Write to [EMAIL] please"
    assert result.decision.outcome == "redact"
    assert result.pii_categories == ["email"]
    interaction = (await rows(database, Interaction))[0]
    assert interaction.pii_categories == ["email"]
    assert interaction.policy_outcome == "redact"
    assert [match.rule_id for match in result.decision.matches] == ["POL-PII-REDACT"]


async def test_no_prompt_text_and_no_personal_data_reach_the_database(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime(ECHO)

    await runtime.chat.complete(context, chat_request(f"A very distinctive sentence for {EMAIL}"))

    assert await text_in_database(database, EMAIL) == []
    assert await text_in_database(database, "distinctive sentence") == []


async def test_text_parts_of_multimodal_messages_are_redacted_too(
    make_runtime: RuntimeFactory, context: TenantContext
) -> None:
    runtime = await make_runtime()
    seen: list[ChatRequest] = []
    provider = runtime.providers["mock"]
    original = provider.chat

    async def spy(request: ChatRequest, target: Any) -> Any:
        seen.append(request)
        return await original(request, target)

    provider.chat = spy
    request = ChatRequest(
        model="gpt-test",
        messages=(
            {"role": "system", "content": None},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"mail {EMAIL}"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
                ],
            },
        ),
    )

    await runtime.chat.complete(context, request)

    assert seen[0].messages[1]["content"] == [
        {"type": "text", "text": "mail [EMAIL]"},
        {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
    ]


async def test_the_hash_strategy_tags_a_value_the_same_way_within_a_tenant(
    make_runtime: RuntimeFactory, context: TenantContext, other_tenant_id: UUID
) -> None:
    runtime = await make_runtime(
        ECHO, redaction={"key": "secret://redaction-key", "default_strategy": "hash"}
    )

    async def reply(ctx: TenantContext) -> str:
        result = await runtime.chat.complete(ctx, chat_request(f"to {EMAIL}"))
        assert result.body is not None
        return str(result.body["choices"][0]["message"]["content"])

    first, again = await reply(context), await reply(context)
    elsewhere = await reply(TenantContext(tenant_id=other_tenant_id))

    assert first == again
    assert first.startswith("to [EMAIL:")
    assert elsewhere != first
    assert EMAIL not in first


async def test_a_model_that_is_not_on_the_allowlist_is_denied_before_any_provider_is_called(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime(policy={"allowed_models": ["another-model"]})

    with pytest.raises(PolicyDeniedError) as raised:
        await runtime.chat.complete(context, chat_request())

    assert [m.rule_id for m in raised.value.decision.matches] == ["POL-MODEL-NOT-ALLOWED"]
    assert runtime.providers["mock"].calls("mock") == 0
    interaction = (await rows(database, Interaction))[0]
    assert interaction.id == raised.value.interaction_id
    assert (interaction.status, interaction.policy_outcome) == ("denied", "deny")
    assert interaction.deployment is None
    assert [(e.action, e.outcome) for e in await audit_entries(database)] == [
        ("chat.policy", "deny")
    ]
    assert (await rows(database, UsageRollup))[0].denied == 1


async def test_a_used_up_hard_budget_denies_the_next_request(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime()
    async with database.transaction() as session:
        await runtime.budgets.create(
            session,
            context.tenant_id,
            scope_type=ScopeType.PROJECT,
            scope_id=context.project_id,
            period=BudgetPeriod.MONTH,
            limit_amount=Decimal("0.000025"),
            hard=True,
        )

    first = await runtime.chat.complete(context, chat_request("x" * 400))
    second = await runtime.chat.complete(context, chat_request("x" * 400))
    with pytest.raises(PolicyDeniedError) as raised:
        await runtime.chat.complete(context, chat_request("x" * 400))

    assert not first.budget.soft_exceeded
    assert second.budget.soft_exceeded
    assert not second.budget.hard_exceeded
    assert [m.rule_id for m in raised.value.decision.matches] == ["POL-BUDGET-EXCEEDED"]
    assert runtime.providers["mock"].calls("mock") == 2


async def test_deny_wins_over_redact_and_both_rules_are_recorded(
    make_runtime: RuntimeFactory, context: TenantContext
) -> None:
    runtime = await make_runtime(policy={"allowed_models": []})

    with pytest.raises(PolicyDeniedError) as raised:
        await runtime.chat.complete(context, chat_request(f"mail {EMAIL}"))

    assert raised.value.decision.outcome == "deny"
    assert [m.rule_id for m in raised.value.decision.matches] == [
        "POL-MODEL-NOT-ALLOWED",
        "POL-PII-REDACT",
    ]


async def test_a_model_no_deployment_serves_is_recorded_as_an_error(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime()

    with pytest.raises(NoRouteError):
        await runtime.chat.complete(context, chat_request(model="unknown-model"))

    interaction = (await rows(database, Interaction))[0]
    assert (interaction.status, interaction.requested_model) == ("error", "unknown-model")
    assert [(e.action, e.outcome) for e in await audit_entries(database)] == [
        ("chat.policy", "allow"),
        ("chat.routing", "no_route"),
    ]


async def test_a_failure_of_every_deployment_is_recorded_with_its_attempts(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime({**MOCK, "settings": {"fail": "retryable"}})

    with pytest.raises(UpstreamError):
        await runtime.chat.complete(context, chat_request())

    interaction = (await rows(database, Interaction))[0]
    assert (interaction.status, interaction.cost_estimate) == ("error", None)
    routing = (await audit_entries(database))[1]
    assert routing.outcome == "failed"
    assert routing.decision is not None
    assert routing.decision["details"]["attempts"] == [
        {"deployment": "mock", "outcome": "error", "error": "ProviderError", "status": 503}
    ]
    assert (await rows(database, UsageRollup))[0].failed == 1


async def test_a_fallback_is_recorded_on_the_deployment_that_answered(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime(
        {**MOCK, "name": "primary", "priority": 1, "settings": {"fail": "retryable"}},
        {**MOCK, "name": "backup", "priority": 2, "model": "mock-large", "region": "westeurope"},
    )

    await runtime.chat.complete(context, chat_request())

    interaction = (await rows(database, Interaction))[0]
    assert (interaction.deployment, interaction.model, interaction.region) == (
        "backup",
        "mock-large",
        "westeurope",
    )
    routing = (await audit_entries(database))[1]
    assert routing.outcome == "route:backup"


async def test_without_usage_from_the_provider_the_interaction_is_unpriced(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime({**MOCK, "settings": {"report_usage": False}})

    await runtime.chat.complete(context, chat_request())

    interaction = (await rows(database, Interaction))[0]
    assert (interaction.input_tokens, interaction.output_tokens) == (None, None)
    assert (interaction.cost_estimate, interaction.currency) == (None, None)
    assert interaction.usage_estimated is False
    assert (await rows(database, UsageRollup))[0].unpriced == 1


async def test_a_deployment_can_opt_in_to_estimated_token_counts(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime(
        {
            **MOCK,
            "usage_fallback": "estimate",
            "chars_per_token": 5,
            "settings": {"report_usage": False, "reply": "y" * 50},
        }
    )

    await runtime.chat.complete(context, chat_request("x" * 100))

    interaction = (await rows(database, Interaction))[0]
    assert (interaction.input_tokens, interaction.output_tokens) == (20, 10)
    assert interaction.usage_estimated is True
    assert interaction.cost_estimate == Decimal("0.000009")
    rollup = (await rows(database, UsageRollup))[0]
    assert (rollup.estimated, rollup.estimated_cost) == (1, Decimal("0.000009"))


async def test_a_model_without_a_price_is_metered_and_unpriced(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime({**MOCK, "model": "no-price-for-this"})

    await runtime.chat.complete(context, chat_request())

    interaction = (await rows(database, Interaction))[0]
    assert interaction.input_tokens is not None
    assert (interaction.cost_estimate, interaction.price_version) == (None, None)


async def test_a_stream_is_relayed_and_recorded_when_it_ends(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime({**MOCK, "settings": {"reply": "one two three"}})

    result = await runtime.chat.stream(context, chat_request("x" * 40, stream=True))
    assert await rows(database, Interaction) == []
    assert result.chunks is not None
    chunks = await collect(result.chunks)

    assert stream_text(chunks) == "one two three"
    assert not any(chunk.usage_only for chunk in chunks)
    interaction = (await rows(database, Interaction))[0]
    assert (interaction.status, interaction.streamed) == ("ok", True)
    assert (interaction.input_tokens, interaction.output_tokens) == (10, 3)
    assert interaction.cost_estimate is not None
    assert len(await audit_entries(database)) == 2


async def test_a_client_that_asks_for_usage_in_the_stream_gets_the_usage_chunk(
    make_runtime: RuntimeFactory, context: TenantContext
) -> None:
    runtime = await make_runtime()
    request = ChatRequest(
        model="gpt-test",
        messages=({"role": "user", "content": "hi"},),
        params={"stream_options": {"include_usage": True}},
        stream=True,
    )

    result = await runtime.chat.stream(context, request)
    assert result.chunks is not None
    chunks = await collect(result.chunks)

    assert chunks[-1].usage_only


async def test_a_stream_the_client_abandons_is_recorded_as_aborted(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime({**MOCK, "settings": {"reply": "one two three four"}})

    result = await runtime.chat.stream(context, chat_request(stream=True))
    assert result.chunks is not None
    iterator = result.chunks.__aiter__()
    await anext(iterator)
    await anext(iterator)
    await iterator.aclose()

    interaction = (await rows(database, Interaction))[0]
    assert interaction.status == "aborted"
    assert interaction.input_tokens is None


async def test_a_stream_the_provider_breaks_halfway_is_recorded_as_an_error(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime(
        {**MOCK, "settings": {"reply": "one two three four", "break_stream_after": 3}}
    )

    result = await runtime.chat.stream(context, chat_request(stream=True))
    assert result.chunks is not None
    received: list[ChatChunk] = []

    async def read() -> None:
        assert result.chunks is not None
        async for chunk in result.chunks:
            received.append(chunk)

    with pytest.raises(ProviderError):
        await read()

    assert stream_text(received) == "one two "
    interaction = (await rows(database, Interaction))[0]
    assert (interaction.status, interaction.deployment) == ("error", "mock")
    assert interaction.cost_estimate is None
    assert [(e.action, e.outcome) for e in await audit_entries(database)] == [
        ("chat.policy", "allow"),
        ("chat.routing", "route:mock"),
    ]


async def test_a_stream_is_denied_before_the_first_chunk(
    make_runtime: RuntimeFactory, context: TenantContext
) -> None:
    runtime = await make_runtime(policy={"allowed_models": []})

    with pytest.raises(PolicyDeniedError):
        await runtime.chat.stream(context, chat_request(stream=True))


async def test_a_stream_that_cannot_start_is_recorded_as_an_error(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime({**MOCK, "settings": {"fail": "retryable"}})

    with pytest.raises(UpstreamError):
        await runtime.chat.stream(context, chat_request(stream=True))
    with pytest.raises(NoRouteError):
        await runtime.chat.stream(context, chat_request(model="unknown", stream=True))

    assert [i.status for i in await rows(database, Interaction)] == ["error", "error"]


async def test_the_prompt_fingerprint_is_stable_per_tenant_and_ignores_spacing(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext, other_tenant_id: UUID
) -> None:
    runtime = await make_runtime()

    await runtime.chat.complete(context, chat_request("What is  the capital\nof Italy?"))
    await runtime.chat.complete(context, chat_request("what is the capital of italy?"))
    await runtime.chat.complete(context, chat_request("Something else"))
    await runtime.chat.complete(
        TenantContext(tenant_id=other_tenant_id), chat_request("what is the capital of italy?")
    )

    async with database.session() as session:
        interactions = (await session.scalars(select(Interaction).order_by(Interaction.id))).all()
    prints = [interaction.prompt_fingerprint for interaction in interactions]
    assert prints[0] == prints[1]
    assert len({prints[0], prints[2], prints[3]}) == 3
    assert all(fingerprint and len(fingerprint) == 64 for fingerprint in prints)


async def test_without_a_redaction_key_no_fingerprint_is_stored(
    make_runtime: RuntimeFactory, database: Database, context: TenantContext
) -> None:
    runtime = await make_runtime(redaction={})

    await runtime.chat.complete(context, chat_request())

    assert (await rows(database, Interaction))[0].prompt_fingerprint is None


def _break_the_audit_log(runtime: GatewayRuntime, monkeypatch: pytest.MonkeyPatch) -> None:
    async def unavailable(*args: object, **kwargs: object) -> None:
        raise OperationalError("INSERT", {}, Exception("disk full"))

    monkeypatch.setattr(runtime.audit, "append", unavailable)


async def test_fail_closed_refuses_a_request_that_cannot_be_audited(
    make_runtime: RuntimeFactory,
    database: Database,
    context: TenantContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = await make_runtime()
    _break_the_audit_log(runtime, monkeypatch)

    with pytest.raises(AuditUnavailableError):
        await runtime.chat.complete(context, chat_request())

    assert await rows(database, Interaction) == []
    assert await rows(database, UsageRollup) == []


async def test_a_tenant_set_to_fail_open_is_answered_even_without_the_audit_entry(
    make_runtime: RuntimeFactory,
    database: Database,
    context: TenantContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = await make_runtime()
    async with database.transaction() as session:
        tenant = await session.get_one(Tenant, context.tenant_id)
        await set_tenant_fail_mode(session, runtime.audit, tenant, "open", actor_id=None)
    _break_the_audit_log(runtime, monkeypatch)

    result = await runtime.chat.complete(context, chat_request())

    assert result.body is not None
    assert await rows(database, Interaction) == []


async def test_a_denial_stands_even_when_it_cannot_be_recorded_under_fail_open(
    make_runtime: RuntimeFactory,
    context: TenantContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = await make_runtime(policy={"allowed_models": []}, audit={"fail_mode": "open"})
    _break_the_audit_log(runtime, monkeypatch)

    with pytest.raises(PolicyDeniedError):
        await runtime.chat.complete(context, chat_request())


async def test_a_custom_policy_pack_replaces_the_default(
    make_runtime: RuntimeFactory, context: TenantContext, tmp_path: Any
) -> None:
    pack = tmp_path / "policy.yaml"
    pack.write_text(
        """
pack: policy
version: "custom-1"
facts: { pii.categories: list, request.stream: boolean }
rules:
  - id: POL-NO-IBAN
    kind: policy
    when: { fact: pii.categories, contains: iban }
    then: { outcome: deny, message_key: policy.model_not_allowed }
""",
        encoding="utf-8",
    )
    runtime = await make_runtime(ECHO, policy={"pack": str(pack)})

    allowed = await runtime.chat.complete(context, chat_request(f"mail {EMAIL}"))
    with pytest.raises(PolicyDeniedError) as raised:
        await runtime.chat.complete(context, chat_request("IBAN IT60X0542811101000000123456"))

    assert allowed.decision.outcome == "allow"
    assert allowed.body is not None
    assert EMAIL in allowed.body["choices"][0]["message"]["content"]
    assert raised.value.decision.details["pack_version"] == "custom-1"
