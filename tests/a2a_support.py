"""Agent Cards for tests, signed with keys made on the spot by the official SDK.

No key is written in this file: each test run generates its own.
"""

import json
from typing import Any

from ai_arbiter.adapters.a2a.signing import CardSigningKey

CARD: dict[str, Any] = {
    "name": "Route planner",
    "description": "Plans routes between two places.",
    "version": "1.4.0",
    "supportedInterfaces": [
        {
            "url": "https://agent.example.org/a2a/v1",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        },
        {
            "url": "https://agent.example.org/a2a/rest",
            "protocolBinding": "HTTP+JSON",
            "protocolVersion": "1.0",
        },
    ],
    "capabilities": {"streaming": True},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {
            "id": "plan",
            "name": "Plan a route",
            "description": "From one place to another.",
            "tags": ["routes"],
        }
    ],
}


# The signing itself is part of the package, where the demonstration uses it too.
SigningKey = CardSigningKey


def unsigned(card: dict[str, Any] | None = None) -> bytes:
    return json.dumps(card if card is not None else CARD).encode()


def tampered(document: bytes, **changes: Any) -> bytes:
    """A signed card with something changed after it was signed."""
    return json.dumps({**json.loads(document), **changes}).encode()
