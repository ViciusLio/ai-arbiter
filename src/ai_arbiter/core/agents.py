"""What Arbiter needs to know of an A2A Agent Card, and the port that reads one.

The card itself is the business of the A2A SDK, which only an adapter imports
(ADR-0052). The rest of Arbiter sees the summary below.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

# Bindings a proxy can stand in front of (ADR-0051). gRPC is not among them.
JSONRPC_BINDING = "JSONRPC"
HTTP_JSON_BINDING = "HTTP+JSON"
GRPC_BINDING = "GRPC"
PROXIED_BINDINGS = (JSONRPC_BINDING, HTTP_JSON_BINDING)


class CardVerification(StrEnum):
    """What the signatures of a card say, against the keys the operator trusts."""

    VERIFIED = "verified"  # one signature verifies with a trusted key
    UNSIGNED = "unsigned"  # the card carries no signature
    UNKNOWN_KEY = "unknown_key"  # it is signed, with no key the operator configured
    INVALID = "invalid"  # a trusted key is named and its signature does not verify


@dataclass(frozen=True)
class AgentInterface:
    binding: str
    url: str
    version: str


@dataclass(frozen=True)
class AgentCardSummary:
    name: str
    version: str
    interfaces: tuple[AgentInterface, ...]
    verification: CardVerification
    # The trusted key a verified or invalid signature names. Null otherwise.
    key_id: str | None = None


class AgentCardReader(Protocol):
    """Parses an Agent Card and verifies its signatures.

    ``keys`` maps a key id to a public key as a JWK. The reader never fetches a key: a
    signature that names a URL for its key set (``jku``) is judged only against
    ``keys`` (ADR-0053). ``algorithms`` lists the signature algorithms accepted.
    """

    name: str

    def read(
        self,
        document: bytes,
        *,
        keys: Mapping[str, Mapping[str, Any]],
        algorithms: Sequence[str],
    ) -> AgentCardSummary:
        """Raises ``ValueError`` for a document that is not an Agent Card."""
        ...
