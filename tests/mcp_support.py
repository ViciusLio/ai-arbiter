"""A stand-in for an MCP server, and the requests a client of revision 2026-07-28 sends.

The server answers through ``httpx.MockTransport``: no socket is opened and no process
is started.
"""

import base64
import json
from typing import Any

import httpx

REVISION = "2026-07-28"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
MCP_URL = "https://tools.example.org/mcp"


class FakeMcpServer:
    """Answers ``server/discover``, ``tools/list`` and ``tools/call`` as a modern server."""

    def __init__(
        self,
        *,
        versions: tuple[str, ...] = (REVISION,),
        tools: tuple[str, ...] = ("read", "write"),
        legacy: bool = False,
        stream: bool = False,
        fail: Exception | None = None,
        redirect: bool = False,
        page_size: int = 100,
    ) -> None:
        self.versions = versions
        self.tools = tools
        self.legacy = legacy
        self.stream = stream
        self.fail = fail
        self.redirect = redirect
        self.page_size = page_size
        self.requests: list[httpx.Request] = []

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def _cacheable(self, **values: Any) -> dict[str, Any]:
        return {"ttlMs": 0, "cacheScope": "private", "resultType": "complete", **values}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail is not None:
            raise self.fail
        if self.redirect:
            return httpx.Response(302, headers={"location": "https://elsewhere.example.org/mcp"})
        if self.legacy:
            # A server of an earlier revision does not know requests without a session.
            return httpx.Response(400, text="Bad Request: no valid session ID provided")
        body = json.loads(request.content)
        method, params = body["method"], body.get("params") or {}
        if request.headers.get("mcp-protocol-version") not in self.versions:
            return httpx.Response(
                400,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {
                        "code": -32022,
                        "message": "Unsupported protocol version",
                        "data": {"supported": list(self.versions), "requested": REVISION},
                    },
                },
            )
        if method == "server/discover":
            result = self._cacheable(
                supportedVersions=list(self.versions), capabilities={"tools": {}}
            )
        elif method == "tools/list":
            start = int(params.get("cursor") or 0)
            page = self.tools[start : start + self.page_size]
            more = start + self.page_size < len(self.tools)
            result = self._cacheable(
                tools=[{"name": name, "inputSchema": {"type": "object"}} for name in page]
            )
            if more:
                result["nextCursor"] = str(start + self.page_size)
        elif method == "tools/call":
            result = {
                "content": [{"type": "text", "text": f"ran {params['name']}"}],
                "resultType": "complete",
            }
        else:
            return httpx.Response(
                404,
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "error": {"code": -32601, "message": "Method not found"},
                },
            )
        answer = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        if self.stream and method == "tools/call":
            progress = {"jsonrpc": "2.0", "method": "notifications/progress", "params": {}}
            events = f"data: {json.dumps(progress)}\n\ndata: {json.dumps(answer)}\n\n"
            return httpx.Response(
                200, headers={"content-type": "text/event-stream"}, content=events.encode()
            )
        return httpx.Response(200, json=answer)


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
