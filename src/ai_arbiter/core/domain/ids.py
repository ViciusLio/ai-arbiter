"""Time-ordered identifiers.

Primary keys are UUIDv7 (RFC 9562): the first 48 bits are the Unix timestamp in
milliseconds, so keys sort by creation time and index well. ``uuid.uuid7`` exists only
from Python 3.14, hence this small implementation (ADR-0024).
"""

import secrets
import time
from uuid import UUID

_TIMESTAMP_MASK = (1 << 48) - 1


def uuid7(*, timestamp_ms: int | None = None) -> UUID:
    """Return a UUIDv7.

    Ordering is by millisecond. Two identifiers created in the same millisecond are in
    random order relative to each other.
    """
    ms = time.time_ns() // 1_000_000 if timestamp_ms is None else timestamp_ms
    value = (ms & _TIMESTAMP_MASK) << 80
    value |= 0x7 << 76  # version
    value |= secrets.randbits(12) << 64  # rand_a
    value |= 0b10 << 62  # variant
    value |= secrets.randbits(62)  # rand_b
    return UUID(int=value)


def new_id() -> UUID:
    """Default identifier factory for every entity."""
    return uuid7()
