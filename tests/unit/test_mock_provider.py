import time
from typing import Any

import pytest

from ai_arbiter.adapters.mock.provider import MockProvider, MockSettings, count_tokens
from ai_arbiter.core.ports.llm import Deployment, ProviderError
from tests.support import chat_request, collect, stream_text


def target(**settings: Any) -> Deployment:
    return Deployment(
        name="mock",
        provider="mock",
        model="mock-small",
        settings=MockSettings(**settings),
    )


async def test_the_reply_has_the_shape_of_a_chat_completion() -> None:
    response = await MockProvider().chat(chat_request("Hello there"), target(reply="Hi!"))

    assert response.body["object"] == "chat.completion"
    assert response.body["model"] == "mock-small"
    assert response.body["choices"][0]["message"] == {"role": "assistant", "content": "Hi!"}
    assert response.body["choices"][0]["finish_reason"] == "stop"


async def test_token_counts_are_deterministic() -> None:
    provider = MockProvider()

    first = await provider.chat(chat_request("x" * 40), target(reply="y" * 20))
    second = await provider.chat(chat_request("x" * 40), target(reply="y" * 20))

    assert first.usage is not None
    assert (first.usage.input_tokens, first.usage.output_tokens) == (10, 5)
    assert second.usage == first.usage
    assert first.body["usage"] == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    assert count_tokens("") == 1


async def test_usage_can_be_withheld() -> None:
    response = await MockProvider().chat(chat_request(), target(report_usage=False))

    assert response.usage is None
    assert "usage" not in response.body


async def test_echo_returns_the_last_user_message() -> None:
    response = await MockProvider().chat(chat_request("repeat me"), target(echo=True))

    assert response.body["choices"][0]["message"]["content"] == "repeat me"


async def test_a_stream_carries_the_reply_and_then_the_usage() -> None:
    chunks = await collect(MockProvider().stream(chat_request(), target(reply="one two three")))

    assert stream_text(chunks) == "one two three"
    assert chunks[0].data["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-2].data["choices"][0]["finish_reason"] == "stop"
    assert chunks[-1].usage_only
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.output_tokens == count_tokens("one two three")
    assert not chunks[0].usage_only


async def test_a_stream_without_usage_ends_with_the_stop_chunk() -> None:
    chunks = await collect(MockProvider().stream(chat_request(), target(report_usage=False)))

    assert all(chunk.usage is None for chunk in chunks)
    assert chunks[-1].data["choices"][0]["finish_reason"] == "stop"


@pytest.mark.parametrize(
    ("mode", "retryable", "status"), [("retryable", True, 503), ("fatal", False, 400)]
)
async def test_failures_can_be_scripted(mode: str, retryable: bool, status: int) -> None:
    with pytest.raises(ProviderError) as raised:
        await MockProvider().chat(chat_request(), target(fail=mode))

    assert raised.value.retryable is retryable
    assert raised.value.status == status


async def test_a_failure_can_be_limited_to_the_first_calls() -> None:
    provider = MockProvider()
    flaky = target(fail="retryable", fail_first=2)

    for _ in range(2):
        with pytest.raises(ProviderError):
            await provider.chat(chat_request(), flaky)
    response = await provider.chat(chat_request(), flaky)

    assert response.body["choices"]
    assert provider.calls("mock") == 3


async def test_a_scripted_failure_stops_a_stream_before_the_first_chunk() -> None:
    with pytest.raises(ProviderError):
        await collect(MockProvider().stream(chat_request(), target(fail="retryable")))


async def test_latency_can_be_scripted() -> None:
    started = time.perf_counter()

    await MockProvider().chat(chat_request(), target(latency_ms=30))

    assert time.perf_counter() - started >= 0.03
