"""The requests a client of MCP revision 2026-07-28 sends. Needs no HTTP library."""

import base64
import json
from typing import Any

REVISION = "2026-07-28"
META_VERSION = "io.modelcontextprotocol/protocolVersion"


def mcp_request(
    method: str,
    *,
    name: str | None = None,
    arguments: dict[str, Any] | None = None,
    request_id: int = 1,
    version: str = REVISION,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    """The body and the headers of one request, as a conforming client builds them."""
    params: dict[str, Any] = {
        "_meta": {
            META_VERSION: version,
            "io.modelcontextprotocol/clientInfo": {"name": "test-client", "version": "1.0"},
            "io.modelcontextprotocol/clientCapabilities": {},
        }
    }
    sent = {
        "content-type": "application/json",
        "accept": "application/json, text/event-stream",
        "mcp-protocol-version": version,
        "mcp-method": method,
    }
    if name is not None:
        params["uri" if method == "resources/read" else "name"] = name
        try:
            name.encode("ascii")
            sent["mcp-name"] = name
        except UnicodeEncodeError:
            sent["mcp-name"] = f"=?base64?{base64.b64encode(name.encode()).decode()}?="
    if arguments is not None:
        params["arguments"] = arguments
    body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    return json.dumps(body).encode(), {**sent, **(headers or {})}
