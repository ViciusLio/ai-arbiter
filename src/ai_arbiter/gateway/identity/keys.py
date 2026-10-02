"""API key format and hashing (ADR-0028).

A key is ``arb_<key id>_<secret><checksum>``. The key id is public and is what the
database is searched by; the secret carries slightly more than 256 bits of randomness;
the checksum lets a malformed key be refused without a database read.
"""

import hashlib
import hmac
import re
import secrets
import string
import zlib
from dataclasses import dataclass

from pydantic import SecretStr

KEY_PREFIX = "arb"
KEY_ID_LENGTH = 12
SECRET_LENGTH = 43
CHECKSUM_LENGTH = 6

_KEY_ID_ALPHABET = string.ascii_lowercase + string.digits
_BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase
_PATTERN = re.compile(
    rf"{KEY_PREFIX}_([a-z0-9]{{{KEY_ID_LENGTH}}})"
    rf"_([0-9A-Za-z]{{{SECRET_LENGTH}}})([0-9A-Za-z]{{{CHECKSUM_LENGTH}}})"
)


@dataclass(frozen=True)
class IssuedKey:
    key_id: str
    plaintext: str

    def __repr__(self) -> str:  # the key must not end up in a log through a repr
        return f"IssuedKey(key_id={self.key_id!r})"


def _checksum(body: str) -> str:
    value = zlib.crc32(body.encode("ascii"))
    digits: list[str] = []
    for _ in range(CHECKSUM_LENGTH):
        value, remainder = divmod(value, len(_BASE62))
        digits.append(_BASE62[remainder])
    return "".join(reversed(digits))


def generate_key() -> IssuedKey:
    key_id = "".join(secrets.choice(_KEY_ID_ALPHABET) for _ in range(KEY_ID_LENGTH))
    secret = "".join(secrets.choice(_BASE62) for _ in range(SECRET_LENGTH))
    body = f"{KEY_PREFIX}_{key_id}_{secret}"
    return IssuedKey(key_id=key_id, plaintext=body + _checksum(body))


def parse_key(presented: str) -> str | None:
    """Return the key id of a well-formed key, or ``None``.

    Well-formed means the right shape and a matching checksum. It says nothing about
    whether the key exists.
    """
    match = _PATTERN.fullmatch(presented)
    if match is None:
        return None
    body = presented[:-CHECKSUM_LENGTH]
    if not hmac.compare_digest(_checksum(body), match.group(3)):
        return None
    return match.group(1)


def hash_key(pepper: SecretStr, key: str) -> str:
    """HMAC-SHA-256 of the whole key, keyed with the pepper, in hexadecimal."""
    return hmac.new(
        pepper.get_secret_value().encode("utf-8"), key.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def display_prefix(key_id: str) -> str:
    """How a key is shown after it was issued: enough to recognise it, nothing secret."""
    return f"{KEY_PREFIX}_{key_id}"
