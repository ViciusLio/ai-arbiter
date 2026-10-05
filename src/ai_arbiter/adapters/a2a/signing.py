"""Sign an A2A Agent Card with a key made on the spot, for the demonstration and for tests.

Nothing here is used to verify a card: that is ``cards.py``, against keys the operator
configured. A key made here lives for one run and is never written anywhere.
"""

import json
from typing import Any

from ai_arbiter.core.errors import MissingExtraError


class CardSigningKey:
    """A fresh P-256 key pair with a key id."""

    def __init__(self, kid: str = "key-1") -> None:
        try:
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError as exc:
            raise MissingExtraError("a2a", "Signing an A2A Agent Card") from exc
        self.kid = kid
        self._private = ec.generate_private_key(ec.SECP256R1())

    @property
    def jwk(self) -> dict[str, Any]:
        """The public key, as an operator would put it in ``a2a.trusted_keys``."""
        from jwt.algorithms import ECAlgorithm

        public: dict[str, Any] = json.loads(ECAlgorithm.to_jwk(self._private.public_key()))
        return {**public, "kid": self.kid}

    def sign(self, card: dict[str, Any], *, jku: str | None = None) -> bytes:
        """The card as JSON, with one ES256 signature over its canonical form."""
        from a2a.types import AgentCard
        from a2a.utils.signing import create_agent_card_signer
        from google.protobuf import json_format

        message = json_format.ParseDict(card, AgentCard())
        header: dict[str, Any] = {"alg": "ES256", "typ": "JOSE", "kid": self.kid}
        if jku is not None:
            header["jku"] = jku
        signed = create_agent_card_signer(self._private, header)(message)  # type: ignore[arg-type]
        return json_format.MessageToJson(signed).encode()
