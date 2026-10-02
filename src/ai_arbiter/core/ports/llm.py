"""Model provider port and the types that cross it (ADR-0013).

The gateway speaks the OpenAI chat completions wire format to its clients and passes
request and response bodies through. These types wrap the bodies with the few things the
gateway itself needs to know: which model, whether it is a stream, how many tokens.
"""

from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from ai_arbiter.core.errors import ArbiterError


class Usage(BaseModel):
    """Token counts as reported by a provider, or estimated when it reported none."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    estimated: bool = False

    @property
    def known(self) -> bool:
        return self.input_tokens is not None and self.output_tokens is not None

    @classmethod
    def from_openai(cls, usage: Any) -> "Usage | None":
        """Read the ``usage`` object of a response or of a stream chunk."""
        if not isinstance(usage, Mapping):
            return None
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if not isinstance(prompt, int) or not isinstance(completion, int):
            return None
        details = usage.get("prompt_tokens_details")
        cached = details.get("cached_tokens") if isinstance(details, Mapping) else None
        return cls(
            input_tokens=prompt,
            output_tokens=completion,
            cached_input_tokens=cached if isinstance(cached, int) else None,
        )


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str  # the name the client asked for, not the name at the provider
    messages: tuple[Mapping[str, Any], ...]
    params: Mapping[str, Any] = {}  # every other field of the request body, untouched
    stream: bool = False

    def texts(self) -> list[str]:
        """Every piece of text in the messages, in order."""
        found: list[str] = []
        for message in self.messages:
            content = message.get("content")
            if isinstance(content, str):
                found.append(content)
            elif isinstance(content, list):
                found.extend(
                    part["text"]
                    for part in content
                    if isinstance(part, Mapping) and isinstance(part.get("text"), str)
                )
        return found


class ChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    body: Mapping[str, Any]  # a chat.completion object
    usage: Usage | None = None


class ChatChunk(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: Mapping[str, Any]  # a chat.completion.chunk object
    usage: Usage | None = None

    @property
    def usage_only(self) -> bool:
        """The extra chunk that carries usage and no choices."""
        return self.usage is not None and not self.data.get("choices")


class Deployment(BaseModel):
    """One place a model can be called: a provider plugin, a model there, its settings."""

    model_config = ConfigDict(frozen=True)

    name: str
    provider: str
    model: str
    region: str | None = None
    settings: BaseModel


class ProviderError(ArbiterError):
    """A provider call failed. The provider's own message is never kept (it may quote
    the prompt); only the status and whether another attempt makes sense."""

    def __init__(self, summary: str, *, retryable: bool, status: int | None = None) -> None:
        self.retryable = retryable
        self.status = status
        super().__init__(summary)


class LLMProvider(Protocol):
    """Implemented by provider plugins, registered under ``ai_arbiter.llm_providers``.

    A plugin class is constructed with the secret store and declares ``settings_model``,
    the Pydantic model that validates the ``settings`` of each of its deployments
    (ADR-0011).
    """

    settings_model: type[BaseModel]

    async def chat(self, request: ChatRequest, target: Deployment) -> ChatResponse:
        """Raises ``ProviderError``."""
        ...

    def stream(self, request: ChatRequest, target: Deployment) -> AsyncIterator[ChatChunk]:
        """Raises ``ProviderError``; before the first chunk if the call was refused."""
        ...

    async def aclose(self) -> None: ...
