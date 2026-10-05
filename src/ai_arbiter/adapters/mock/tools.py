"""Stand-ins for an MCP server and an A2A agent, for the demonstration and for tests.

Both answer in process through an HTTP transport: no socket is opened, no program is
started and no real model is involved (ADR-0033). They speak just enough of each
protocol to show Arbiter standing in front of them.
"""

import json
from typing import Any

from ai_arbiter.core.errors import MissingExtraError

MCP_REVISION = "2026-07-28"
DEMO_MCP_URL = "https://tools.demo.invalid/mcp"
DEMO_AGENT_HOST = "https://agent.demo.invalid"
DEMO_CARD_URL = f"{DEMO_AGENT_HOST}/.well-known/agent-card.json"
DEMO_AGENT_RPC = f"{DEMO_AGENT_HOST}/a2a/v1"

DEMO_CARD: dict[str, Any] = {
    "name": "Demo route planner",
    "description": "An invented agent that plans routes. It exists only in the demonstration.",
    "version": "1.0.0",
    "supportedInterfaces": [
        {"url": DEMO_AGENT_RPC, "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
    ],
    "capabilities": {},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {"id": "plan", "name": "Plan a route", "description": "Invented.", "tags": ["demo"]}
    ],
}


def _httpx() -> Any:
    try:
        import httpx
    except ImportError as exc:
        raise MissingExtraError("gateway", "The demonstration") from exc
    return httpx


class MockToolWorld:
    """One handler for both stand-ins. ``card`` is what the agent serves as its card."""

    def __init__(self, tools: tuple[str, ...] = ("read", "write")) -> None:
        self.tools = tools
        self.card: bytes = json.dumps(DEMO_CARD).encode()

    def transport(self) -> Any:
        return _httpx().MockTransport(self)

    def _mcp(self, request: Any) -> Any:
        httpx = _httpx()
        body = json.loads(request.content)
        method, params = body["method"], body.get("params") or {}
        base = {"ttlMs": 0, "cacheScope": "private", "resultType": "complete"}
        if method == "server/discover":
            result = {**base, "supportedVersions": [MCP_REVISION], "capabilities": {"tools": {}}}
        elif method == "tools/list":
            result = {
                **base,
                "tools": [{"name": name, "inputSchema": {"type": "object"}} for name in self.tools],
            }
        elif method == "tools/call":
            text = f"the mock server ran the tool '{params.get('name')}'"
            result = {"content": [{"type": "text", "text": text}], "resultType": "complete"}
        else:
            error = {"code": -32601, "message": "Method not found"}
            return httpx.Response(404, json={"jsonrpc": "2.0", "id": body["id"], "error": error})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    def __call__(self, request: Any) -> Any:
        httpx = _httpx()
        url = str(request.url)
        if url == DEMO_MCP_URL:
            return self._mcp(request)
        if url == DEMO_CARD_URL:
            return httpx.Response(200, content=self.card)
        if url == DEMO_AGENT_RPC:
            body = json.loads(request.content)
            task = {"task": {"id": "demo-task", "status": {"state": "TASK_STATE_COMPLETED"}}}
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": task})
        return httpx.Response(404)
