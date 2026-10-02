"""OpenAI wire format over HTTP: OpenAI itself, Ollama, vLLM and most hosted services.

The HTTP client is part of the ``gateway`` extra and is imported when the first call is
made, so that naming this plugin on a base install fails with an instruction.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_arbiter.core.config.secrets import SecretRef
from ai_arbiter.core.errors import MissingExtraError
from ai_arbiter.core.ports import SecretStore
from ai_arbiter.core.ports.llm import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    Deployment,
    ProviderError,
    Usage,
)

# Statuses after which another attempt makes sense, because the request itself was not at
# fault: the provider is overloaded or failing, or this deployment is misconfigured
# (wrong key, unknown model) and another one may not be.
RETRYABLE_STATUS = frozenset({401, 403, 404, 408, 409, 425, 429, 500, 502, 503, 504})


class OpenAICompatSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Up to and including the version segment, for example https://api.openai.com/v1
    base_url: str
    # A secret reference (secret://NAME), never the key itself. Omit for local servers.
    api_key: str | None = None
    timeout_seconds: int = Field(default=120, ge=1)

    @field_validator("api_key")
    @classmethod
    def _reference(cls, value: str | None) -> str | None:
        if value is not None:
            SecretRef.parse(value)
        return value


class OpenAIWireProvider:
    """Shared behaviour of the adapters that speak the OpenAI wire format."""

    settings_model: type[BaseModel] = OpenAICompatSettings
    feature = "The OpenAI-compatible provider"

    def __init__(self, secrets: SecretStore, *, transport: Any = None) -> None:
        self._secrets = secrets
        self._transport = transport
        self._client: Any = None

    def _http(self) -> Any:
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise MissingExtraError("gateway", self.feature) from exc
            self._client = httpx.AsyncClient(transport=self._transport)
        return self._client

    # What differs between flavours

    def _url(self, target: Deployment) -> str:
        settings = self._settings(target)
        return settings.base_url.rstrip("/") + "/chat/completions"

    async def _headers(self, target: Deployment) -> dict[str, str]:
        settings = self._settings(target)
        if settings.api_key is None:
            return {}
        key = await self._secrets.get(SecretRef.parse(settings.api_key))
        return {"Authorization": f"Bearer {key.get_secret_value()}"}

    def _timeout(self, target: Deployment) -> int:
        return self._settings(target).timeout_seconds

    def _body(self, request: ChatRequest, target: Deployment) -> dict[str, Any]:
        return {**request.params, "model": target.model, "messages": list(request.messages)}

    @staticmethod
    def _settings(target: Deployment) -> OpenAICompatSettings:
        settings = target.settings
        if not isinstance(settings, OpenAICompatSettings):
            raise ProviderError("deployment settings do not match the provider", retryable=False)
        return settings

    # Calls

    @staticmethod
    def _refused(status: int) -> ProviderError:
        return ProviderError(
            f"provider returned HTTP {status}",
            retryable=status in RETRYABLE_STATUS,
            status=status,
        )

    async def chat(self, request: ChatRequest, target: Deployment) -> ChatResponse:
        client = self._http()
        import httpx

        body = {**self._body(request, target), "stream": False}
        body.pop("stream_options", None)
        try:
            response = await client.post(
                self._url(target),
                json=body,
                headers=await self._headers(target),
                timeout=self._timeout(target),
            )
        except httpx.TransportError as exc:
            raise ProviderError(
                f"provider unreachable: {type(exc).__name__}", retryable=True
            ) from exc
        if response.status_code != 200:
            raise self._refused(response.status_code)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError(
                "provider returned a body that is not JSON", retryable=True
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderError("provider returned an unexpected body", retryable=True)
        return ChatResponse(body=payload, usage=Usage.from_openai(payload.get("usage")))

    async def stream(self, request: ChatRequest, target: Deployment) -> AsyncIterator[ChatChunk]:
        client = self._http()
        import httpx

        body = self._body(request, target)
        options = body.get("stream_options")
        # Always ask for usage: without it a streamed call cannot be metered (ADR-0031).
        body["stream_options"] = {
            **(options if isinstance(options, dict) else {}),
            "include_usage": True,
        }
        body["stream"] = True
        try:
            async with client.stream(
                "POST",
                self._url(target),
                json=body,
                headers=await self._headers(target),
                timeout=self._timeout(target),
            ) as response:
                if response.status_code != 200:
                    raise self._refused(response.status_code)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        return
                    try:
                        payload = json.loads(data)
                    except ValueError as exc:
                        raise ProviderError(
                            "provider sent a stream event that is not JSON", retryable=False
                        ) from exc
                    if isinstance(payload, dict):
                        yield ChatChunk(data=payload, usage=Usage.from_openai(payload.get("usage")))
        except httpx.TransportError as exc:
            raise ProviderError(
                f"provider unreachable: {type(exc).__name__}", retryable=True
            ) from exc

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


class OpenAICompatProvider(OpenAIWireProvider):
    """Registered as ``openai_compat``."""
