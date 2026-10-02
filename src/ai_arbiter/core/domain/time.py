"""Time helpers. Every timestamp in Arbiter is timezone-aware and in UTC."""

from datetime import UTC, datetime
from typing import Protocol


def utcnow() -> datetime:
    return datetime.now(UTC)


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """Default implementation of the ``Clock`` port."""

    def now(self) -> datetime:
        return utcnow()
