"""Data plane: the OpenAI-compatible endpoints."""

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ai_arbiter.core.ports.llm import ChatChunk, ChatRequest, ProviderError
from ai_arbiter.gateway.api.deps import Caller, Runtime
from ai_arbiter.gateway.chat import ChatResult

router = APIRouter(prefix="/v1", tags=["models"])


class ChatCompletionRequest(BaseModel):
    """An OpenAI chat completion request. Fields not listed here are passed through."""

    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(min_length=1)
    stream: bool = False


class ModelInfo(BaseModel):
    id: str
    object: Literal["model"] = "model"
    owned_by: str = "arbiter"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelInfo]


def _headers(result: ChatResult) -> dict[str, str]:
    headers = {
        "X-Arbiter-Interaction-Id": str(result.interaction_id),
        "X-Arbiter-Decision-Id": str(result.decision.id),
        "X-Arbiter-Policy": result.decision.outcome,
        "X-Arbiter-Budget": "soft" if result.budget.soft_exceeded else "ok",
    }
    if result.pii_categories:
        headers["X-Arbiter-Redacted"] = ",".join(result.pii_categories)
    return headers


async def _events(chunks: AsyncIterator[ChatChunk]) -> AsyncIterator[str]:
    """Server-sent events in the OpenAI format, ending with ``[DONE]``."""
    try:
        async for chunk in chunks:
            yield f"data: {json.dumps(chunk.data, separators=(',', ':'))}\n\n"
    except ProviderError:
        # The stream broke after it had started: say so in-band, without the provider's
        # own message.
        error = {"message": "the model provider ended the stream", "type": "upstream_error"}
        yield f"data: {json.dumps({'error': error}, separators=(',', ':'))}\n\n"
    yield "data: [DONE]\n\n"


@router.post(
    "/chat/completions",
    summary="Create a chat completion",
    description="OpenAI-compatible. The request is checked by policy, routed to a deployment "
    "that serves the model, metered and audited. Prompt and completion text is not stored. "
    "A request stopped by policy returns 403 with the decision and its reasons.",
    response_class=JSONResponse,
)
async def chat_completions(
    body: ChatCompletionRequest, runtime: Runtime, caller: Caller
) -> Response:
    request = ChatRequest(
        model=body.model,
        messages=tuple(body.messages),
        params=body.model_extra or {},
        stream=body.stream,
    )
    if body.stream:
        result = await runtime.chat.stream(caller.context, request)
        assert result.chunks is not None  # noqa: S101 - stream() always sets it
        return StreamingResponse(
            _events(result.chunks),
            media_type="text/event-stream",
            headers={**_headers(result), "Cache-Control": "no-cache"},
        )
    result = await runtime.chat.complete(caller.context, request)
    return JSONResponse(result.body, headers=_headers(result))


@router.get(
    "/models",
    summary="List models",
    description="The model names this gateway serves and policy allows.",
)
async def list_models(runtime: Runtime, caller: Caller) -> ModelList:
    allowed = runtime.settings.policy.allowed_models
    return ModelList(
        data=[
            ModelInfo(id=model)
            for model in runtime.router.models()
            if allowed is None or model in allowed
        ]
    )
