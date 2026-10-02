from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy.dialects import sqlite

from ai_arbiter.core.domain.ids import new_id, uuid7
from ai_arbiter.core.domain.tenancy import TenantContext
from ai_arbiter.core.domain.time import SystemClock, utcnow
from ai_arbiter.core.persistence.types import UTCDateTime


def test_uuid7_has_version_and_variant_bits() -> None:
    value = uuid7()

    assert value.version == 7
    assert value.variant == "specified in RFC 4122"


def test_uuid7_embeds_the_timestamp_in_the_leading_bits() -> None:
    value = uuid7(timestamp_ms=1_700_000_000_123)

    assert value.int >> 80 == 1_700_000_000_123


def test_uuid7_sorts_by_creation_time() -> None:
    earlier = uuid7(timestamp_ms=1_000)
    later = uuid7(timestamp_ms=1_001)

    assert earlier < later
    assert str(earlier) < str(later)


def test_new_id_is_unique() -> None:
    assert len({new_id() for _ in range(1_000)}) == 1_000


def test_clock_returns_aware_utc_time() -> None:
    for value in (utcnow(), SystemClock().now()):
        assert value.tzinfo is UTC


def test_tenant_context_is_immutable() -> None:
    context = TenantContext(tenant_id=UUID(int=1))

    with pytest.raises(ValueError, match="frozen"):
        context.tenant_id = UUID(int=2)  # type: ignore[misc]


class TestUTCDateTime:
    column = UTCDateTime()
    dialect = sqlite.dialect()

    def test_rejects_naive_values(self) -> None:
        with pytest.raises(ValueError, match="naive"):
            self.column.process_bind_param(datetime(2026, 1, 1, 12, 0), self.dialect)  # noqa: DTZ001

    def test_converts_to_utc_on_the_way_in(self) -> None:
        rome = timezone(timedelta(hours=2))

        stored = self.column.process_bind_param(
            datetime(2026, 7, 1, 12, 0, tzinfo=rome), self.dialect
        )

        assert stored == datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
        assert stored is not None
        assert stored.tzinfo is UTC

    def test_reads_naive_values_as_utc(self) -> None:
        loaded = self.column.process_result_value(datetime(2026, 7, 1, 10, 0), self.dialect)  # noqa: DTZ001

        assert loaded == datetime(2026, 7, 1, 10, 0, tzinfo=UTC)

    def test_normalises_aware_values_on_the_way_out(self) -> None:
        rome = timezone(timedelta(hours=2))

        loaded = self.column.process_result_value(
            datetime(2026, 7, 1, 12, 0, tzinfo=rome), self.dialect
        )

        assert loaded is not None
        assert loaded.tzinfo is UTC
        assert loaded.hour == 10

    def test_passes_none_through(self) -> None:
        assert self.column.process_bind_param(None, self.dialect) is None
        assert self.column.process_result_value(None, self.dialect) is None
