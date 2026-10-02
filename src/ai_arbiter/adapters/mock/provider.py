"""Mock model provider: deterministic, scriptable, in-process (ADR-0013)."""

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ai_arbiter.core.ports import SecretStore
from ai_arbiter.core.ports.llm import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    Deployment,
    ProviderError,
    Usage,
)


class MockSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reply: str = "This is a reply from the mock provider."
    # Answer with the last user message instead of ``reply``.
    echo: bool = False
    latency_ms: int = Field(default=0, ge=0)
    fail: Literal["never", "retryable", "fatal"] = "never"
    # With ``fail`` set: fail this many calls, then succeed. 0 means fail every call.
    fail_first: int = Field(default=0, ge=0)
    report_usage: bool = True
    # Streams only: break the stream after this many chunks, as a provider that fails
    # halfway does.
    break_stream_after: int | None = Field(default=None, ge=1)


def count_tokens(text: str) -> int:
    """A stand-in for a tokenizer: one token per four characters, at least one."""
    return max(1, len(text) // 4)


class MockProvider:
    settings_model: type[BaseModel] = MockSettings

    def __init__(self, secrets: SecretStore | None = None) -> None:
        self._calls: dict[str, int] = defaultdict(int)

    def calls(self, deployment: str) -> int:
        """How many times a deployment was called. For tests."""
        return self._calls[deployment]

    async def _enter(self, target: Deployment) -> MockSettings:
        settings = target.settings
        if not isinstance(settings, MockSettings):
            raise ProviderError("mock deployment has no mock settings", retryable=False)
        self._calls[target.name] += 1
        if settings.latency_ms:
            await asyncio.sleep(settings.latency_ms / 1000)
        if settings.fail != "never" and (
            settings.fail_first == 0 or self._calls[target.name] <= settings.fail_first
        ):
            retryable = settings.fail == "retryable"
            raise ProviderError(
                "mock provider failure", retryable=retryable, status=503 if retryable else 400
            )
        return settings

    @staticmethod
    def _reply(request: ChatRequest, settings: MockSettings) -> str:
        if not settings.echo:
            return settings.reply
        for message in reversed(request.messages):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                return str(message["content"])
        return settings.reply

    @staticmethod
    def _usage(request: ChatRequest, reply: str) -> Usage:
        return Usage(
            input_tokens=sum(count_tokens(text) for text in request.texts()),
            output_tokens=count_tokens(reply),
        )

    @staticmethod
    def _usage_body(usage: Usage) -> dict[str, Any]:
        return {
            "prompt_tokens": usage.input_tokens,
            "completion_tokens": usage.output_tokens,
            "total_tokens": (usage.input_tokens or 0) + (usage.output_tokens or 0),
        }

    async def chat(self, request: ChatRequest, target: Deployment) -> ChatResponse:
        settings = await self._enter(target)
        reply = self._reply(request, settings)
        usage = self._usage(request, reply) if settings.report_usage else None
        body: dict[str, Any] = {
            "id": f"chatcmpl-mock-{self._calls[target.name]}",
            "object": "chat.completion",
            "created": 0,
            "model": target.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": reply},
                    "finish_reason": "stop",
                }
            ],
        }
        if usage is not None:
            body["usage"] = self._usage_body(usage)
        return ChatResponse(body=body, usage=usage)

    async def stream(self, request: ChatRequest, target: Deployment) -> AsyncIterator[ChatChunk]:
        settings = await self._enter(target)
        reply = self._reply(request, settings)
        base = {
            "id": f"chatcmpl-mock-{self._calls[target.name]}",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": target.model,
        }

        def chunk(delta: dict[str, Any], finish: str | None = None) -> ChatChunk:
            choice = {"index": 0, "delta": delta, "finish_reason": finish}
            return ChatChunk(data={**base, "choices": [choice]})

        yield chunk({"role": "assistant", "content": ""})
        words = reply.split(" ")
        for position, word in enumerate(words):
            if (
                settings.break_stream_after is not None
                and position + 1 >= settings.break_stream_after
            ):
                raise ProviderError("mock provider broke the stream", retryable=False)
            yield chunk({"content": word if position == len(words) - 1 else word + " "})
        yield chunk({}, "stop")
        if settings.report_usage:
            usage = self._usage(request, reply)
            yield ChatChunk(
                data={**base, "choices": [], "usage": self._usage_body(usage)}, usage=usage
            )

    async def aclose(self) -> None:
        return None
