"""Import interaction records of an external source into the canonical table."""

import json
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.compliance.inventory.model import AISystem
from ai_arbiter.core.audit import AuditRecord
from ai_arbiter.core.config.settings import IngestMapping
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.errors import ArbiterError
from ai_arbiter.core.interaction import Interaction, InteractionRecord
from ai_arbiter.core.ports import AuditLog, TelemetrySource

# Stores an interaction. The command line passes the usage meter, so that imported
# records are counted in the roll-ups; the default only adds the row.
Sink = Callable[[AsyncSession, Interaction], Awaitable[None]]
MAX_REPORTED_LINES = 20


class IngestError(ArbiterError):
    """An import was stopped."""


@dataclass
class IngestReport:
    source: str
    read: int = 0
    imported: int = 0
    duplicates: int = 0
    unattributed: int = 0
    attributed: dict[str, int] = field(default_factory=dict)
    unknown_systems: set[str] = field(default_factory=set)
    # Line numbers of records that could not be read, and how many there were in all.
    invalid_lines: list[int] = field(default_factory=list)
    invalid: int = 0


async def _add(session: AsyncSession, interaction: Interaction) -> None:
    session.add(interaction)


class IngestService:
    def __init__(
        self, audit: AuditLog, mappings: Sequence[IngestMapping] = (), sink: Sink | None = None
    ) -> None:
        self._audit = audit
        self._mappings = mappings
        self._sink = sink if sink is not None else _add

    def _system_key(self, record: InteractionRecord) -> str | None:
        """Attribution order of ADR-0019: the source's own tag, then a configured mapping."""
        if record.system:
            return record.system
        for mapping in self._mappings:
            if mapping.source is not None and mapping.source != record.source:
                continue
            if mapping.labels and all(
                record.labels.get(name) == value for name, value in mapping.labels.items()
            ):
                return mapping.system
            if not mapping.labels and mapping.source is not None:
                return mapping.system
        return None

    async def ingest(
        self,
        session: AsyncSession,
        tenant_id: UUID,
        lines: Iterable[str],
        source: TelemetrySource,
        *,
        strict: bool = False,
        actor_id: UUID | None = None,
    ) -> IngestReport:
        """Read records, one JSON object per line, and store the new ones.

        Idempotent on the source and its record id: a record imported before is counted
        as a duplicate and left alone. A line that cannot be read is skipped and
        reported by number, without its content; with ``strict`` it stops the import.
        """
        report = IngestReport(source=source.name)
        systems: dict[str, UUID | None] = {}
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            report.read += 1
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("not a JSON object")
                record = source.parse(payload)
            except ValueError as error:
                if strict:
                    reason = "not valid JSON" if isinstance(error, json.JSONDecodeError) else error
                    raise IngestError(f"line {number}: {reason}") from error
                report.invalid += 1
                if len(report.invalid_lines) < MAX_REPORTED_LINES:
                    report.invalid_lines.append(number)
                continue

            existing = await session.scalar(
                select(Interaction.id).where(
                    Interaction.tenant_id == tenant_id,
                    Interaction.source == record.source,
                    Interaction.source_record_id == record.source_record_id,
                )
            )
            if existing is not None:
                report.duplicates += 1
                continue

            key = self._system_key(record)
            system_id: UUID | None = None
            if key is not None:
                if key not in systems:
                    systems[key] = await session.scalar(
                        select(AISystem.id).where(
                            AISystem.tenant_id == tenant_id, AISystem.key == key
                        )
                    )
                system_id = systems[key]
                if system_id is None:
                    report.unknown_systems.add(key)
            if system_id is None:
                report.unattributed += 1
            else:
                report.attributed[key or ""] = report.attributed.get(key or "", 0) + 1

            await self._sink(
                session,
                Interaction(
                    id=new_id(),
                    tenant_id=tenant_id,
                    ai_system_id=system_id,
                    source=record.source,
                    source_record_id=record.source_record_id,
                    started_at=record.started_at,
                    duration_ms=record.duration_ms,
                    operation=record.operation,
                    requested_model=record.requested_model,
                    provider=record.provider,
                    model=record.model,
                    region=record.region,
                    status=record.status.value,
                    streamed=record.streamed,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    cached_input_tokens=record.cached_input_tokens,
                    usage_estimated=record.usage_estimated,
                    cost_estimate=(
                        Decimal(record.cost_estimate) if record.cost_estimate is not None else None
                    ),
                    currency=record.currency if record.cost_estimate is not None else None,
                    # The cost is the source's figure, not one from Arbiter's catalogue.
                    price_version=(
                        f"source:{record.source}" if record.cost_estimate is not None else None
                    ),
                    pii_categories=sorted(set(record.pii_categories)),
                ),
            )
            report.imported += 1
            await session.flush()

        await self._audit.append(
            session,
            tenant_id,
            AuditRecord(
                action="ingest.completed",
                outcome=f"imported:{report.imported}",
                actor_id=actor_id,
                resource_type="telemetry_source",
                resource_id=source.name,
                decision={
                    "read": report.read,
                    "imported": report.imported,
                    "duplicates": report.duplicates,
                    "invalid": report.invalid,
                    "unattributed": report.unattributed,
                },
            ),
        )
        return report
