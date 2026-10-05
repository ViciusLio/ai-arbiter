"""Agent Cards for tests, signed with keys made on the spot by the official SDK.

No key is written in this file: each test run generates its own.
"""

import json
from typing import Any

from a2a.types import AgentCard
from a2a.utils.signing import create_agent_card_signer
from cryptography.hazmat.primitives.asymmetric import ec
from google.protobuf import json_format
from jwt.algorithms import ECAlgorithm

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


class SigningKey:
    """A fresh P-256 key pair with a key id."""

    def __init__(self, kid: str = "key-1") -> None:
        self.kid = kid
        self._private = ec.generate_private_key(ec.SECP256R1())

    @property
    def jwk(self) -> dict[str, Any]:
        """The public key, as an operator would put it in the configuration."""
        public = json.loads(ECAlgorithm.to_jwk(self._private.public_key()))
        return {**public, "kid": self.kid}

    def sign(self, card: dict[str, Any], *, jku: str | None = None) -> bytes:
        message = json_format.ParseDict(card, AgentCard())
        header: dict[str, Any] = {"alg": "ES256", "typ": "JOSE", "kid": self.kid}
        if jku is not None:
            header["jku"] = jku
        signed = create_agent_card_signer(self._private, header)(message)  # type: ignore[arg-type]
        return json_format.MessageToJson(signed).encode()


def unsigned(card: dict[str, Any] | None = None) -> bytes:
    return json.dumps(card if card is not None else CARD).encode()


def tampered(document: bytes, **changes: Any) -> bytes:
    """A signed card with something changed after it was signed."""
    return json.dumps({**json.loads(document), **changes}).encode()
