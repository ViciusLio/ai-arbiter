"""Which A2A operation a request is, for the two bindings the proxy speaks (ADR-0051).

The proxy forwards only the operations A2A 1.0 defines. A request that is none of them
is not forwarded: what cannot be named cannot be authorized or recorded. The content of
a request, the message an agent is sent or the task it returns, is never read.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai_arbiter.core.errors import ArbiterError

VERSION_HEADER = "a2a-version"
EXTENSIONS_HEADER = "a2a-extensions"

# Arbiter refused the call, or could not reach the agent. Outside the range A2A keeps
# for its own errors (-32001 to -32099).
DENIED = -32000

# JSON-RPC method -> operation.
JSONRPC_METHODS: Mapping[str, str] = {
    "SendMessage": "send_message",
    "SendStreamingMessage": "send_streaming_message",
    "GetTask": "get_task",
    "ListTasks": "list_tasks",
    "CancelTask": "cancel_task",
    "SubscribeToTask": "subscribe_task",
    "CreateTaskPushNotificationConfig": "push_config_create",
    "GetTaskPushNotificationConfig": "push_config_get",
    "ListTaskPushNotificationConfigs": "push_config_list",
    "DeleteTaskPushNotificationConfig": "push_config_delete",
    "GetExtendedAgentCard": "get_extended_card",
}

_ID = r"[A-Za-z0-9._~-]{1,200}"
# (HTTP verb, path pattern) -> operation, for the HTTP+JSON binding.
_REST_ROUTES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("POST", re.compile(r"message:send"), "send_message"),
    ("POST", re.compile(r"message:stream"), "send_streaming_message"),
    ("GET", re.compile(rf"tasks/{_ID}"), "get_task"),
    ("GET", re.compile(r"tasks"), "list_tasks"),
    ("POST", re.compile(rf"tasks/{_ID}:cancel"), "cancel_task"),
    ("POST", re.compile(rf"tasks/{_ID}:subscribe"), "subscribe_task"),
    ("POST", re.compile(rf"tasks/{_ID}/pushNotificationConfigs"), "push_config_create"),
    ("GET", re.compile(rf"tasks/{_ID}/pushNotificationConfigs/{_ID}"), "push_config_get"),
    ("GET", re.compile(rf"tasks/{_ID}/pushNotificationConfigs"), "push_config_list"),
    ("DELETE", re.compile(rf"tasks/{_ID}/pushNotificationConfigs/{_ID}"), "push_config_delete"),
    ("GET", re.compile(r"extendedAgentCard"), "get_extended_card"),
)


class A2aRequestError(ArbiterError):
    """A request the proxy rejects before any decision."""

    def __init__(
        self, status: int, code: int, message: str, *, request_id: int | str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id


@dataclass(frozen=True)
class JsonRpcCall:
    request_id: int | str
    operation: str


def parse_jsonrpc(body: bytes) -> JsonRpcCall:
    """The operation of a JSON-RPC request. Raises ``A2aRequestError``."""
    try:
        payload: Any = json.loads(body)
    except ValueError as exc:
        raise A2aRequestError(400, -32700, "Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise A2aRequestError(400, -32600, "the body must be one JSON-RPC request, not a batch")
    raw_id = payload.get("id")
    request_id = raw_id if isinstance(raw_id, int | str) and not isinstance(raw_id, bool) else None
    method = payload.get("method")
    if payload.get("jsonrpc") != "2.0" or not isinstance(method, str) or request_id is None:
        raise A2aRequestError(
            400, -32600, "Request payload validation error", request_id=request_id
        )
    operation = JSONRPC_METHODS.get(method)
    if operation is None:
        raise A2aRequestError(404, -32601, "Method not found", request_id=request_id)
    return JsonRpcCall(request_id=request_id, operation=operation)


def rest_operation(verb: str, path: str) -> str | None:
    """The operation behind a request of the HTTP+JSON binding, or ``None``.

    Only the shapes A2A defines match, so a path cannot walk out of the agent's
    interface.
    """
    for route_verb, pattern, operation in _REST_ROUTES:
        if route_verb == verb.upper() and pattern.fullmatch(path):
            return operation
    return None


def jsonrpc_error(
    code: int,
    message: str,
    *,
    request_id: int | str | None = None,
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = dict(data)
    body: dict[str, Any] = {"jsonrpc": "2.0", "error": error}
    if request_id is not None:
        body["id"] = request_id
    return body


def forwarded_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """The request headers an agent needs. Never the caller's own credential."""
    kept = {"accept": headers.get("accept") or "application/json, text/event-stream"}
    for name in ("content-type", VERSION_HEADER, EXTENSIONS_HEADER):
        if name in headers:
            kept[name] = headers[name]
    return kept
