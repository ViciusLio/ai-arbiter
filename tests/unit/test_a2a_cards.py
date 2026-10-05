"""Reading an Agent Card and judging its signatures against trusted keys (ADR-0053)."""

import pytest

pytest.importorskip("a2a", reason="needs the a2a extra")

from ai_arbiter.adapters.a2a.cards import SdkAgentCardReader
from ai_arbiter.core.agents import AgentCardReader, AgentInterface, CardVerification
from ai_arbiter.core.plugins.registry import AGENT_CARD_READERS, PluginRegistry
from tests.a2a_support import CARD, SigningKey, tampered, unsigned

ALGORITHMS = ["ES256"]


@pytest.fixture
def reader() -> SdkAgentCardReader:
    return SdkAgentCardReader()


def test_the_reader_is_a_plugin_and_satisfies_the_port() -> None:
    loaded = PluginRegistry().load(AGENT_CARD_READERS, "a2a")()
    port: AgentCardReader = loaded

    assert (port.name, type(loaded)) == ("a2a", SdkAgentCardReader)


def test_a_card_signed_with_a_trusted_key_is_verified(reader: SdkAgentCardReader) -> None:
    key = SigningKey()

    summary = reader.read(key.sign(CARD), keys={key.kid: key.jwk}, algorithms=ALGORITHMS)

    assert (summary.name, summary.version) == ("Route planner", "1.4.0")
    assert summary.interfaces == (
        AgentInterface("JSONRPC", "https://agent.example.org/a2a/v1", "1.0"),
        AgentInterface("HTTP+JSON", "https://agent.example.org/a2a/rest", "1.0"),
    )
    assert (summary.verification, summary.key_id) == (CardVerification.VERIFIED, "key-1")


def test_an_unsigned_card_is_read_and_said_to_be_unsigned(reader: SdkAgentCardReader) -> None:
    key = SigningKey()

    summary = reader.read(unsigned(), keys={key.kid: key.jwk}, algorithms=ALGORITHMS)

    assert (summary.verification, summary.key_id) == (CardVerification.UNSIGNED, None)
    assert len(summary.interfaces) == 2


def test_a_key_the_card_brings_with_it_is_not_trusted(reader: SdkAgentCardReader) -> None:
    theirs = SigningKey("their-key")
    ours = SigningKey("our-key")
    # The card says where its key set is. Nothing is fetched from there.
    document = theirs.sign(CARD, jku="https://agent.example.org/jwks.json")

    summary = reader.read(document, keys={ours.kid: ours.jwk}, algorithms=ALGORITHMS)
    no_keys = reader.read(document, keys={}, algorithms=ALGORITHMS)

    assert (summary.verification, summary.key_id) == (CardVerification.UNKNOWN_KEY, None)
    assert no_keys.verification is CardVerification.UNKNOWN_KEY


def test_a_card_changed_after_signing_does_not_verify(reader: SdkAgentCardReader) -> None:
    key = SigningKey()
    document = tampered(key.sign(CARD), description="Plans routes and reads your mail.")

    summary = reader.read(document, keys={key.kid: key.jwk}, algorithms=ALGORITHMS)

    assert (summary.verification, summary.key_id) == (CardVerification.INVALID, "key-1")


def test_a_trusted_key_id_with_another_key_behind_it_does_not_verify(
    reader: SdkAgentCardReader,
) -> None:
    impostor = SigningKey("key-1")
    trusted = SigningKey("key-1")

    summary = reader.read(
        impostor.sign(CARD), keys={trusted.kid: trusted.jwk}, algorithms=ALGORITHMS
    )

    assert summary.verification is CardVerification.INVALID


def test_an_algorithm_that_is_not_accepted_does_not_verify(reader: SdkAgentCardReader) -> None:
    key = SigningKey()

    summary = reader.read(key.sign(CARD), keys={key.kid: key.jwk}, algorithms=["RS256"])

    assert summary.verification is CardVerification.INVALID


@pytest.mark.parametrize(
    "document",
    [b"not json", b"[]", b'{"description": "no name"}', b'{"name": ""}', b"\xff\xfe"],
)
def test_a_document_that_is_not_a_card_is_refused(
    reader: SdkAgentCardReader, document: bytes
) -> None:
    with pytest.raises(ValueError, match="not an A2A Agent Card"):
        reader.read(document, keys={}, algorithms=ALGORITHMS)
