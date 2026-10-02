"""Opt-in checks of the OpenAI-compatible adapter against a real server (ADR-0033).

Skipped unless ``ARBITER_LIVE_OPENAI_BASE_URL`` is set, which CI never does. To repeat
the check of 2026-10-02 against Ollama in a container:

    docker run -d --name arbiter-ollama -p 127.0.0.1:11434:11434 ollama/ollama
    docker exec arbiter-ollama ollama pull smollm2:135m
    ARBITER_LIVE_OPENAI_BASE_URL=http://127.0.0.1:11434/v1 \\
    ARBITER_LIVE_OPENAI_MODEL=smollm2:135m uv run pytest tests/live -v
    docker rm -f -v arbiter-ollama && docker rmi ollama/ollama   # the image is 9.3 GB

``ARBITER_LIVE_OPENAI_API_KEY`` is sent as the bearer token when set. Prompts are
synthetic. What the model answers is not asserted, only the shape of the exchange.
"""

import os
from uuid import UUID

import pytest

BASE_URL = os.environ.get("ARBITER_LIVE_OPENAI_BASE_URL")
MODEL = os.environ.get("ARBITER_LIVE_OPENAI_MODEL", "")
API_KEY = os.environ.get("ARBITER_LIVE_OPENAI_API_KEY")

pytestmark = [
    pytest.mark.skipif(not BASE_URL, reason="opt-in: set ARBITER_LIVE_OPENAI_BASE_URL"),
    pytest.mark.usefixtures("gateway_secrets"),
]

pytest.importorskip("fastapi", reason="needs the gateway extra")

from sqlalchemy import select  # noqa: E402

from ai_arbiter.adapters.local.secrets import EnvSecretStore  # noqa: E402
from ai_arbiter.adapters.openai_compat.provider import (  # noqa: E402
    OpenAICompatProvider,
    OpenAICompatSettings,
)
from ai_arbiter.core.domain.tenancy import AccessRole  # noqa: E402
from ai_arbiter.core.interaction import Interaction  # noqa: E402
from ai_arbiter.core.persistence.database import Database  # noqa: E402
from ai_arbiter.core.ports.llm import ChatRequest, Deployment, ProviderError  # noqa: E402
from tests.api_support import app_for, issue_key, running  # noqa: E402
from tests.support import collect, stream_text  # noqa: E402

PROMPT = "Reply with one short sentence about the colour of the sky."


def provider() -> OpenAICompatProvider:
    return OpenAICompatProvider(EnvSecretStore({"ARBITER_SECRET_LIVE_KEY": API_KEY or ""}))


def target(model: str = MODEL) -> Deployment:
    return Deployment(
        name="live",
        provider="openai_compat",
        model=model,
        settings=OpenAICompatSettings(
            base_url=BASE_URL or "", api_key="secret://live-key" if API_KEY else None
        ),
    )


def request(*, stream: bool = False) -> ChatRequest:
    return ChatRequest(
        model="public-name",
        messages=({"role": "user", "content": PROMPT},),
        params={"max_tokens": 40, "temperature": 0},
        stream=stream,
    )


async def test_a_real_server_answers_a_completion_with_usage() -> None:
    live = provider()
    try:
        response = await live.chat(request(), target())
    finally:
        await live.aclose()

    assert response.body["choices"][0]["message"]["role"] == "assistant"
    assert isinstance(response.body["choices"][0]["message"]["content"], str)
    assert response.usage is not None
    assert response.usage.known
    assert (response.usage.input_tokens or 0) > 0


async def test_a_real_server_streams_text_and_then_usage() -> None:
    live = provider()
    try:
        chunks = await collect(live.stream(request(stream=True), target()))
    finally:
        await live.aclose()

    assert len(chunks) > 2
    assert stream_text(chunks).strip()
    assert chunks[-1].usage is not None, "the server ignored stream_options.include_usage"
    assert chunks[-1].usage.known


async def test_a_real_server_refuses_an_unknown_model_with_a_status() -> None:
    live = provider()
    try:
        with pytest.raises(ProviderError) as raised:
            await live.chat(request(), target("no-such-model-arbiter-live-check"))
    finally:
        await live.aclose()

    assert raised.value.status in (400, 404)


async def test_a_request_goes_through_the_whole_gateway_to_a_real_server(
    database: Database, tenant_id: UUID
) -> None:
    deployment = {
        "name": "live",
        "provider": "openai_compat",
        "model": MODEL,
        "serves": ["public-name"],
        "settings": {"base_url": BASE_URL},
    }
    app = app_for(database.engine.url.render_as_string(False), deployment)
    body = {
        "model": "public-name",
        "max_tokens": 40,
        "messages": [{"role": "user", "content": PROMPT + " Contact: test@example.com"}],
    }
    async with running(app) as client:
        key = await issue_key(app, tenant_id, AccessRole.DEVELOPER)
        plain = await client.post("/v1/chat/completions", json=body, headers=key.auth)
        streamed = await client.post(
            "/v1/chat/completions", json={**body, "stream": True}, headers=key.auth
        )

    assert plain.status_code == 200, plain.text
    assert plain.headers["x-arbiter-redacted"] == "email"
    assert plain.json()["choices"][0]["message"]["content"]
    assert streamed.status_code == 200
    assert streamed.text.rstrip().endswith("data: [DONE]")
    async with database.session() as session:
        interactions = (await session.scalars(select(Interaction).order_by(Interaction.id))).all()
    assert [(i.status, i.streamed, i.deployment) for i in interactions] == [
        ("ok", False, "live"),
        ("ok", True, "live"),
    ]
    assert all(i.input_tokens and i.output_tokens and not i.usage_estimated for i in interactions)
    assert all(i.cost_estimate is None for i in interactions)  # no price was configured
