import re

from pydantic import SecretStr

from ai_arbiter.gateway.identity.keys import (
    display_prefix,
    generate_key,
    hash_key,
    parse_key,
)

PEPPER = SecretStr("a-pepper-of-at-least-thirty-two-characters")


def test_a_generated_key_has_the_documented_shape() -> None:
    issued = generate_key()

    assert re.fullmatch(r"arb_[a-z0-9]{12}_[0-9A-Za-z]{49}", issued.plaintext)
    assert issued.plaintext.startswith(f"arb_{issued.key_id}_")


def test_generated_keys_do_not_repeat() -> None:
    keys = {generate_key().plaintext for _ in range(200)}

    assert len(keys) == 200


def test_parsing_a_generated_key_returns_its_key_id() -> None:
    issued = generate_key()

    assert parse_key(issued.plaintext) == issued.key_id


def test_a_key_with_one_character_changed_fails_the_checksum() -> None:
    issued = generate_key()
    position = len("arb_") + 12 + 1 + 5
    replacement = "A" if issued.plaintext[position] != "A" else "B"
    tampered = issued.plaintext[:position] + replacement + issued.plaintext[position + 1 :]

    assert parse_key(tampered) is None


def test_malformed_keys_are_rejected_without_an_error() -> None:
    issued = generate_key().plaintext

    for presented in ["", "arb_", "sk-something", issued[:-1], issued + "x", issued.upper()]:
        assert parse_key(presented) is None


def test_the_hash_depends_on_the_pepper_and_on_the_key() -> None:
    first, second = generate_key().plaintext, generate_key().plaintext

    assert hash_key(PEPPER, first) == hash_key(PEPPER, first)
    assert hash_key(PEPPER, first) != hash_key(PEPPER, second)
    assert hash_key(PEPPER, first) != hash_key(SecretStr("another-pepper" * 3), first)
    assert re.fullmatch(r"[0-9a-f]{64}", hash_key(PEPPER, first))


def test_the_repr_of_an_issued_key_does_not_contain_it() -> None:
    issued = generate_key()

    assert issued.plaintext not in repr(issued)


def test_the_display_prefix_is_the_public_part_only() -> None:
    issued = generate_key()

    assert display_prefix(issued.key_id) == issued.plaintext[:16]
