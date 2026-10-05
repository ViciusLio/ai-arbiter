"""Pass the answer of an upstream server on to the caller, for the MCP and A2A proxies."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from fastapi import Response
from fastapi.responses import StreamingResponse


class Completion(Protocol):
    def __call__(
        self,
        *,
        status_code: int | None,
        response_bytes: int | None,
        streamed: bool,
        reason: str | None = None,
    ) -> Awaitable[None]: ...


async def relay(
    upstream: Any,
    *,
    max_bytes: int,
    complete: Completion,
    failure: Callable[[], Response],
) -> Response:
    """Relay an open upstream response and record how it ended through ``complete``.

    An event stream is passed on as it arrives. Anything else is read whole, up to
    ``max_bytes``, and passed on with its status and content type. The body is relayed
    decoded: how the upstream compressed it is not passed on. ``failure`` builds the
    answer when the body cannot be relayed.
    """
    content_type = upstream.headers.get("content-type", "application/json")
    if content_type.startswith("text/event-stream"):

        async def stream() -> AsyncIterator[bytes]:
            sent = 0
            reason: str | None = None
            try:
                async for chunk in upstream.aiter_bytes():
                    sent += len(chunk)
                    yield chunk
            except Exception as error:
                reason = type(error).__name__
                raise
            finally:
                await upstream.aclose()
                await complete(
                    status_code=upstream.status_code,
                    response_bytes=sent,
                    streamed=True,
                    reason=reason,
                )

        return StreamingResponse(
            stream(),
            status_code=upstream.status_code,
            media_type=content_type,
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
        )

    received = b""
    reason: str | None = None
    try:
        async for chunk in upstream.aiter_bytes():
            received += chunk
            if len(received) > max_bytes:
                reason = "ResponseTooLarge"
                break
    except Exception as error:  # the connection broke while the answer was being read
        reason = type(error).__name__
    finally:
        await upstream.aclose()
    await complete(
        status_code=upstream.status_code,
        response_bytes=len(received),
        streamed=False,
        reason=reason,
    )
    if reason is not None:
        return failure()
    return Response(
        content=received,
        status_code=upstream.status_code,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )
