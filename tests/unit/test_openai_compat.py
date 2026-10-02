import json
import sys
from collections.abc import Callable
from typing import Any

import pytest

pytest.importorskip("httpx", reason="needs the gateway extra")

import httpx

from ai_arbiter.adapters.azure.openai import AzureOpenAIProvider, AzureOpenAISettings
from ai_arbiter.adapters.local.secrets import EnvSecretStore
from ai_arbiter.adapters.openai_compat.provider import (
    OpenAICompatProvider,
    OpenAICompatSettings,
    OpenAIWireProvider,
)
from ai_arbiter.core.errors import MissingExtraError, SecretNotFoundError
from ai_arbiter.core.ports.llm import ChatRequest, Deployment, ProviderError
from tests.support import chat_request, collect, stream_text

SECRETS = EnvSecretStore(
    {"ARBITER_SECRET_OPENAI_KEY": "sk-test", "ARBITER_SECRET_AZURE_KEY": "az-test"}
)
COMPLETION = {
    "id": "chatcmpl-1",
    "object": "chat.completion",
    "model": "gpt-upstream",
    "choices": [
        {"index": 0, "message": {"role": "assistant", "content": "Hi"}, "finish_reason": "stop"}
    ],
    "usage": {
        "prompt_tokens": 12,
        "completion_tokens": 3,
        "total_tokens": 15,
        "prompt_tokens_details": {"cached_tokens": 4},
    },
}


def openai_target(**settings: Any) -> Deployment:
    values: dict[str, Any] = {
        "base_url": "https://llm.example/v1/",
        "api_key": "secret://openai-key",
        **settings,
    }
    return Deployment(
        name="primary",
        provider="openai_compat",
        model="gpt-upstream",
        settings=OpenAICompatSettings(**values),
    )


def azure_target() -> Deployment:
    return Deployment(
        name="azure",
        provider="azure_openai",
        model="my-deployment",
        settings=AzureOpenAISettings(
            endpoint="https://res.openai.azure.com/",
            api_version="2024-10-21",
            api_key="secret://azure-key",
        ),
    )


Handler = Callable[[httpx.Request], httpx.Response]


def provider_with(
    handler: Handler | httpx.Response, cls: type[OpenAIWireProvider] = OpenAICompatProvider
) -> tuple[OpenAIWireProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler if isinstance(handler, httpx.Response) else handler(request)

    return cls(SECRETS, transport=httpx.MockTransport(record)), seen


def sse(*events: object) -> httpx.Response:
    body = "".join(
        f"data: {event if isinstance(event, str) else json.dumps(event)}\n\n" for event in events
    )
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


async def test_a_completion_is_passed_through_with_its_usage() -> None:
    provider, seen = provider_with(httpx.Response(200, json=COMPLETION))
    request = ChatRequest(
        model="gpt-public",
        messages=({"role": "user", "content": "Hello"},),
        params={"temperature": 0, "max_tokens": 50, "stream_options": {"include_usage": True}},
    )

    response = await provider.chat(request, openai_target())

    assert response.body == COMPLETION
    assert response.usage is not None
    assert (response.usage.input_tokens, response.usage.output_tokens) == (12, 3)
    assert response.usage.cached_input_tokens == 4
    sent = json.loads(seen[0].content)
    assert str(seen[0].url) == "https://llm.example/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer sk-test"
    assert sent == {
        "model": "gpt-upstream",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0,
        "max_tokens": 50,
        "stream": False,
    }


async def test_no_authorization_header_without_a_key() -> None:
    provider, seen = provider_with(httpx.Response(200, json=COMPLETION))

    await provider.chat(chat_request(), openai_target(api_key=None))

    assert "authorization" not in seen[0].headers


async def test_a_completion_without_usage_reports_none() -> None:
    body = {key: value for key, value in COMPLETION.items() if key != "usage"}
    provider, _ = provider_with(httpx.Response(200, json=body))

    response = await provider.chat(chat_request(), openai_target())

    assert response.usage is None


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(429, True), (500, True), (503, True), (401, True), (404, True), (400, False), (422, False)],
)
async def test_http_errors_say_whether_another_attempt_makes_sense(
    status: int, retryable: bool
) -> None:
    provider, _ = provider_with(
        httpx.Response(status, json={"error": {"message": "the prompt was: SECRET PROMPT"}})
    )

    with pytest.raises(ProviderError) as raised:
        await provider.chat(chat_request(), openai_target())

    assert raised.value.retryable is retryable
    assert raised.value.status == status
    assert "SECRET PROMPT" not in str(raised.value)


async def test_a_connection_failure_is_retryable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider, _ = provider_with(refuse)

    with pytest.raises(ProviderError, match="provider unreachable: ConnectError") as raised:
        await provider.chat(chat_request(), openai_target())

    assert raised.value.retryable


@pytest.mark.parametrize("content", [b"<html>gateway</html>", b"[1, 2]"])
async def test_a_body_that_is_not_a_completion_is_an_error(content: bytes) -> None:
    provider, _ = provider_with(httpx.Response(200, content=content))

    with pytest.raises(ProviderError):
        await provider.chat(chat_request(), openai_target())


async def test_a_missing_secret_is_reported_as_such() -> None:
    provider, _ = provider_with(httpx.Response(200, json=COMPLETION))

    with pytest.raises(SecretNotFoundError):
        await provider.chat(chat_request(), openai_target(api_key="secret://absent"))


def test_the_key_must_be_a_secret_reference() -> None:
    with pytest.raises(ValueError, match="not a secret reference"):
        OpenAICompatSettings(base_url="https://llm.example/v1", api_key="sk-live-123")
    with pytest.raises(ValueError, match="not a secret reference"):
        AzureOpenAISettings(endpoint="https://x", api_version="v", api_key="plain")


async def test_a_stream_is_parsed_and_always_asks_for_usage() -> None:
    usage = {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9}
    provider, seen = provider_with(
        sse(
            {"choices": [{"index": 0, "delta": {"role": "assistant", "content": "Hel"}}]},
            {"choices": [{"index": 0, "delta": {"content": "lo"}, "finish_reason": "stop"}]},
            {"choices": [], "usage": usage},
            "[DONE]",
        )
    )

    chunks = await collect(provider.stream(chat_request(stream=True), openai_target()))

    assert stream_text(chunks) == "Hello"
    assert chunks[-1].usage_only
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.input_tokens == 7
    sent = json.loads(seen[0].content)
    assert sent["stream"] is True
    assert sent["stream_options"] == {"include_usage": True}


async def test_a_stream_refused_by_the_provider_fails_before_the_first_chunk() -> None:
    provider, _ = provider_with(httpx.Response(429, json={"error": "slow down"}))

    with pytest.raises(ProviderError) as raised:
        await collect(provider.stream(chat_request(stream=True), openai_target()))

    assert raised.value.retryable


async def test_a_malformed_stream_event_is_an_error() -> None:
    provider, _ = provider_with(sse("{not json"))

    with pytest.raises(ProviderError, match="not JSON"):
        await collect(provider.stream(chat_request(stream=True), openai_target()))


async def test_azure_uses_the_deployment_url_and_the_api_key_header() -> None:
    provider, seen = provider_with(httpx.Response(200, json=COMPLETION), AzureOpenAIProvider)

    response = await provider.chat(chat_request(), azure_target())

    assert response.usage is not None
    assert str(seen[0].url) == (
        "https://res.openai.azure.com/openai/deployments/my-deployment/chat/completions"
        "?api-version=2024-10-21"
    )
    assert seen[0].headers["api-key"] == "az-test"
    assert "authorization" not in seen[0].headers
    assert "model" not in json.loads(seen[0].content)


async def test_settings_of_the_wrong_provider_are_refused() -> None:
    provider, _ = provider_with(httpx.Response(200, json=COMPLETION), AzureOpenAIProvider)

    with pytest.raises(ProviderError, match="do not match"):
        await provider.chat(chat_request(), openai_target())


async def test_the_client_is_closed_with_the_provider() -> None:
    provider, _ = provider_with(httpx.Response(200, json=COMPLETION))
    await provider.chat(chat_request(), openai_target())

    await provider.aclose()
    await provider.aclose()


async def test_without_the_http_client_the_extra_to_install_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "httpx", None)

    with pytest.raises(MissingExtraError, match=r"ai-arbiter\[gateway\]"):
        await OpenAICompatProvider(SECRETS).chat(chat_request(), openai_target())
