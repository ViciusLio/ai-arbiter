"""Read an A2A Agent Card and verify its signatures with the official SDK.

The SDK is part of the ``a2a`` extra and is imported when a card is first read, so that
naming this plugin on an install without the extra fails with an instruction.
"""

import base64
import binascii
import json
from collections.abc import Mapping, Sequence
from typing import Any

from ai_arbiter.core.agents import AgentCardSummary, AgentInterface, CardVerification
from ai_arbiter.core.errors import MissingExtraError

_FEATURE = "Reading an A2A Agent Card"


def _protected_key_id(protected: str) -> str | None:
    """The key id in the protected header of a signature, or ``None`` if unreadable."""
    try:
        padded = protected + "=" * (-len(protected) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
    except (binascii.Error, ValueError):
        return None
    kid = header.get("kid") if isinstance(header, dict) else None
    return kid if isinstance(kid, str) and kid else None


class SdkAgentCardReader:
    """The ``AgentCardReader`` port, on ``a2a-sdk``."""

    name = "a2a"

    def read(
        self,
        document: bytes,
        *,
        keys: Mapping[str, Mapping[str, Any]],
        algorithms: Sequence[str],
    ) -> AgentCardSummary:
        try:
            import jwt
            from a2a.types import AgentCard
            from a2a.utils.signing import SignatureVerificationError, create_signature_verifier
            from google.protobuf import json_format
        except ImportError as exc:
            raise MissingExtraError("a2a", _FEATURE) from exc

        try:
            card = json_format.Parse(document, AgentCard(), ignore_unknown_fields=True)
        except (json_format.ParseError, UnicodeDecodeError) as exc:
            raise ValueError("the document is not an A2A Agent Card") from exc
        if not card.name:
            raise ValueError("the document is not an A2A Agent Card: it has no name")

        interfaces = tuple(
            AgentInterface(
                binding=interface.protocol_binding,
                url=interface.url,
                version=interface.protocol_version,
            )
            for interface in card.supported_interfaces
        )
        named = [_protected_key_id(signature.protected) for signature in card.signatures]
        trusted = [kid for kid in named if kid is not None and kid in keys]
        if not card.signatures:
            verification, key_id = CardVerification.UNSIGNED, None
        elif not trusted:
            verification, key_id = CardVerification.UNKNOWN_KEY, None
        else:
            key_id = trusted[0]

            def provide(kid: str | None, jku: str | None) -> Any:
                # Only keys the operator configured. Where the card says its keys are
                # (jku) is not looked at: nothing is fetched (ADR-0053).
                if kid is None or kid not in keys:
                    raise jwt.InvalidKeyError("not a trusted key")
                return jwt.PyJWK(dict(keys[kid]))

            try:
                create_signature_verifier(provide, list(algorithms))(card)
            except (SignatureVerificationError, jwt.PyJWTError):
                verification = CardVerification.INVALID
            else:
                verification = CardVerification.VERIFIED
        return AgentCardSummary(
            name=card.name,
            version=card.version,
            interfaces=interfaces,
            verification=verification,
            key_id=key_id,
        )
