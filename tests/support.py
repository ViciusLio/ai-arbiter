"""Helpers shared by tests."""

from collections.abc import AsyncIterator, Sequence
from typing import Any

from ai_arbiter.adapters.local.secrets import EnvSecretStore
from ai_arbiter.core.config import DeploymentSettings, RouterSettings
from ai_arbiter.core.plugins import PluginRegistry
from ai_arbiter.core.ports.llm import ChatChunk, ChatRequest
from ai_arbiter.gateway.llm_router.deployments import Target, build_targets
from ai_arbiter.gateway.llm_router.router import CostOf, Router


def chat_request(
    text: str = "Hello there", *, model: str = "gpt-test", stream: bool = False
) -> ChatRequest:
    return ChatRequest(model=model, messages=({"role": "user", "content": text},), stream=stream)


def deployment(name: str, **overrides: Any) -> DeploymentSettings:
    values: dict[str, Any] = {
        "name": name,
        "provider": "mock",
        "model": f"{name}-model",
        "serves": ("gpt-test",),
    }
    values.update(overrides)
    return DeploymentSettings(**values)


def mock_router(
    deployments: Sequence[DeploymentSettings],
    *,
    cost_of: CostOf | None = None,
    **router: Any,
) -> tuple[Router, list[Target], Any]:
    """A router over mock deployments. Returns it with its targets and the mock provider."""
    targets, providers = build_targets(deployments, PluginRegistry(), EnvSecretStore({}))
    settings = RouterSettings(**{"retry_backoff_ms": 0, **router})
    return Router(targets, providers, settings, cost_of=cost_of), targets, providers.get("mock")


async def collect(chunks: AsyncIterator[ChatChunk]) -> list[ChatChunk]:
    return [chunk async for chunk in chunks]


def stream_text(chunks: Sequence[ChatChunk]) -> str:
    return "".join(
        choice.get("delta", {}).get("content") or ""
        for chunk in chunks
        for choice in chunk.data.get("choices", [])
    )
