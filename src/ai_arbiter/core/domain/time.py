"""Time helpers. Every timestamp in Arbiter is timezone-aware and in UTC."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


class SystemClock:
    """Default implementation of the ``Clock`` port."""

    def now(self) -> datetime:
        return utcnow()
