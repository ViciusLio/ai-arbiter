"""What the MCP proxy checks of a request before it decides anything (ADR-0046).

Revision ``2026-07-28`` mirrors the protocol version, the method and the name of the
tool into HTTP headers, and requires whoever reads the body to reject a request whose
headers disagree with it: otherwise one component could decide on the header while
another acts on the body. The proxy reads the body, so it validates.

The messages and the constants come from the official ``mcp-types`` package (ADR-0050),
imported when first used so that the rest of the gateway works without the extra.
"""

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from ai_arbiter.core.errors import ArbiterError, MissingExtraError
from ai_arbiter.gateway.mcp.catalogue import MODERN_REVISION

SUPPORTED_REVISIONS = (MODERN_REVISION,)

PROTOCOL_HEADER = "mcp-protocol-version"
METHOD_HEADER = "mcp-method"
NAME_HEADER = "mcp-name"
PARAM_HEADER_PREFIX = "mcp-param-"

# Methods that name what they act on, and the field of ``params`` that holds the name.
NAMED_METHODS: Mapping[str, str] = {
    "tools/call": "name",
    "prompts/get": "name",
    "resources/read": "uri",
}
TOOL_CALL = "tools/call"
TOOL_LIST = "tools/list"
# Methods that only say what a server offers. Any grant on the server allows them.
LISTING_METHODS = frozenset(
    {
        "server/discover",
        "tools/list",
        "prompts/list",
        "resources/list",
        "resources/templates/list",
    }
)

# Arbiter refused the call. From the range the specification leaves to implementations.
DENIED = -32010
UPSTREAM_FAILED = -32011

_SENTINEL_PREFIX = "=?base64?"
_SENTINEL_SUFFIX = "?="


def types() -> ModuleType:
    """The official MCP message types. Raises ``MissingExtraError`` without the extra."""
    try:
        import mcp_types
    except ImportError as exc:
        raise MissingExtraError("mcp", "The MCP proxy") from exc
    return mcp_types


class ProtocolError(ArbiterError):
    """A request the proxy rejects before any decision, as the specification requires."""

    def __init__(
        self,
        status: int,
        code: int,
        message: str,
        *,
        request_id: int | str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.request_id = request_id
        self.data = data


@dataclass(frozen=True)
class McpRequest:
    request_id: int | str
    method: str
    # The tool or the prompt called, or the address of the resource read.
    name: str | None

    @property
    def tool(self) -> str | None:
        return self.name if self.method == TOOL_CALL else None

    @property
    def recorded_name(self) -> str | None:
        """What is kept of the name: never the address of a resource."""
        return self.name if self.method in ("tools/call", "prompts/get") else None


def error_body(
    code: int,
    message: str,
    *,
    request_id: int | str | None = None,
    data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """A JSON-RPC error response. The id is left out when the request had none to read."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = dict(data)
    body: dict[str, Any] = {"jsonrpc": "2.0", "error": error}
    if request_id is not None:
        body["id"] = request_id
    return body


def decode_header_value(value: str) -> str:
    """A header value, decoded when it uses the Base64 form for what ASCII cannot carry."""
    if not (value.startswith(_SENTINEL_PREFIX) and value.endswith(_SENTINEL_SUFFIX)):
        return value
    encoded = value[len(_SENTINEL_PREFIX) : -len(_SENTINEL_SUFFIX)]
    try:
        return base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("not valid Base64") from exc


def parse_request(body: bytes, headers: Mapping[str, str]) -> McpRequest:
    """Read one JSON-RPC request and check it against its headers.

    ``headers`` has lower-case names. Raises ``ProtocolError`` with the HTTP status and
    the JSON-RPC error the specification names for each case. Nothing of the request is
    echoed back except the two values a header mismatch is about.
    """
    mcp = types()
    codes = mcp.jsonrpc
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise ProtocolError(400, codes.PARSE_ERROR, "the body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ProtocolError(
            400, codes.INVALID_REQUEST, "the body must be one JSON-RPC request, not a batch"
        )
    raw_id = payload.get("id")
    request_id = raw_id if isinstance(raw_id, int | str) and not isinstance(raw_id, bool) else None
    method = payload.get("method")
    if payload.get("jsonrpc") != "2.0" or not isinstance(method, str) or not method:
        raise ProtocolError(
            400, codes.INVALID_REQUEST, "not a JSON-RPC 2.0 request", request_id=request_id
        )
    if "result" in payload or "error" in payload:
        raise ProtocolError(
            400,
            codes.INVALID_REQUEST,
            "a client sends requests, not responses",
            request_id=request_id,
        )
    if request_id is None:
        # The core protocol defines no client notification over Streamable HTTP.
        raise ProtocolError(
            400, codes.INVALID_REQUEST, "notifications are not forwarded: a request needs an id"
        )
    params = payload.get("params")
    if params is not None and not isinstance(params, dict):
        raise ProtocolError(
            400, codes.INVALID_REQUEST, "params must be an object", request_id=request_id
        )
    params = params or {}

    def mismatch(message: str) -> ProtocolError:
        return ProtocolError(400, codes.HEADER_MISMATCH, message, request_id=request_id)

    version = headers.get(PROTOCOL_HEADER)
    if not version:
        raise mismatch("Header mismatch: the MCP-Protocol-Version header is missing")
    if version not in SUPPORTED_REVISIONS:
        raise ProtocolError(
            400,
            mcp.UNSUPPORTED_PROTOCOL_VERSION,
            "Unsupported protocol version",
            request_id=request_id,
            data={"supported": list(SUPPORTED_REVISIONS), "requested": version[:32]},
        )
    meta = params.get("_meta")
    declared = meta.get(mcp.PROTOCOL_VERSION_META_KEY) if isinstance(meta, dict) else None
    if declared != version:
        raise mismatch(
            "Header mismatch: the MCP-Protocol-Version header does not match the protocol "
            "version in the body"
        )
    if headers.get(METHOD_HEADER) != method:
        raise mismatch("Header mismatch: the Mcp-Method header does not match the method")

    name: str | None = None
    field = NAMED_METHODS.get(method)
    if field is not None:
        value = params.get(field)
        if not isinstance(value, str) or not value:
            raise ProtocolError(
                400,
                codes.INVALID_PARAMS,
                f"{method} needs params.{field}",
                request_id=request_id,
            )
        mirrored = headers.get(NAME_HEADER)
        if not mirrored:
            raise mismatch("Header mismatch: the Mcp-Name header is missing")
        try:
            decoded = decode_header_value(mirrored)
        except ValueError as exc:
            raise mismatch("Header mismatch: the Mcp-Name header is not valid") from exc
        if decoded != value:
            raise mismatch(f"Header mismatch: the Mcp-Name header does not match params.{field}")
        name = value
    return McpRequest(request_id=request_id, method=method, name=name)


def forwarded_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """The request headers an MCP server needs, and nothing else of what the client sent.

    The caller's own credential is never among them: the server gets the credential of
    the catalogue, if any.
    """
    kept = {
        "content-type": "application/json",
        "accept": headers.get("accept") or "application/json, text/event-stream",
    }
    for name in (PROTOCOL_HEADER, METHOD_HEADER, NAME_HEADER):
        if name in headers:
            kept[name] = headers[name]
    # A header the proxy does not recognise is forwarded and otherwise ignored.
    for name, value in headers.items():
        if name.startswith(PARAM_HEADER_PREFIX):
            kept[name] = value
    return kept


def keep_tools(content_type: str, body: bytes, allowed: frozenset[str]) -> bytes | None:
    """The answer to ``tools/list`` with only the tools named in ``allowed``.

    Only the names are read. An answer that carries an error is passed on as it is; one
    that cannot be read as a JSON-RPC response gives nothing, and is not relayed.
    """
    answer = read_response(content_type, body)
    if answer is None:
        return None
    result = answer.get("result")
    if isinstance(result, dict):
        tools = result.get("tools")
        if not isinstance(tools, list):
            return None
        result["tools"] = [
            tool for tool in tools if isinstance(tool, dict) and tool.get("name") in allowed
        ]
    elif "error" not in answer:
        return None
    return json.dumps(answer, separators=(",", ":")).encode()


def read_response(content_type: str, body: bytes) -> dict[str, Any] | None:
    """The JSON-RPC response in a body: one JSON object, or the last one of an event stream."""
    text = body.decode("utf-8", errors="replace")
    found: Any = None
    if content_type.startswith("text/event-stream"):
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    candidate = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(candidate, dict) and ("result" in candidate or "error" in candidate):
                    found = candidate
    else:
        try:
            found = json.loads(text)
        except ValueError:
            found = None
    return found if isinstance(found, dict) else None
