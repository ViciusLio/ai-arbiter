"""Column types that behave the same on PostgreSQL and SQLite."""

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import BigInteger, DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware timestamp, always stored and returned in UTC.

    SQLite has no timezone support and returns naive values; they are read back as UTC.
    Naive values are rejected on the way in, so a local time can never be stored by
    mistake.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime is not allowed; use a timezone-aware value")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


AMOUNT_SCALE = 9
AMOUNT_QUANTUM = Decimal(1).scaleb(-AMOUNT_SCALE)


def quantize_amount(value: Decimal) -> Decimal:
    """Round to the precision amounts are stored with: nine decimal places."""
    return value.quantize(AMOUNT_QUANTUM, rounding=ROUND_HALF_EVEN)


class DecimalAmount(TypeDecorator[Decimal]):
    """A money amount, exact on every database (ADR-0030).

    SQLite has no decimal type and would store a float. The amount is therefore stored
    as an integer number of billionths of the currency unit, which sums exactly in SQL,
    and is a ``Decimal`` in code. The range is about nine billion units.
    """

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> int | None:
        if value is None:
            return None
        if not isinstance(value, Decimal):
            raise TypeError("amounts must be Decimal, not float or int")
        return int(quantize_amount(value).scaleb(AMOUNT_SCALE))

    def process_result_value(self, value: int | None, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        return Decimal(int(value)).scaleb(-AMOUNT_SCALE)
