"""Audit log on the database: append, verify, export (ADR-0017, ADR-0023)."""

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_arbiter.core.audit.chain import (
    ChainVerifier,
    VerificationReport,
    entry_hash,
    export_entry,
    export_head,
    export_header,
    format_timestamp,
    genesis_hash,
)
from ai_arbiter.core.audit.model import AuditChainHead, AuditEntry
from ai_arbiter.core.canonical_json import JsonValue
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.domain.time import Clock, SystemClock
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.core.rules.decision import Decision

FailMode = Literal["closed", "open"]


class AuditRecord(BaseModel):
    """What happened. No content, no names: identifiers and outcomes only."""

    model_config = ConfigDict(frozen=True)

    action: str
    outcome: str
    actor_id: UUID | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    decision: Mapping[str, JsonValue] | None = None

    @classmethod
    def of_decision(
        cls,
        decision: Decision,
        *,
        action: str,
        actor_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> "AuditRecord":
        return cls(
            action=action,
            outcome=decision.outcome,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            decision=decision.audit_payload(),
        )


class AuditReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_id: UUID
    seq: int
    entry_hash: str


def entry_body(entry: AuditEntry) -> dict[str, Any]:
    """The part of an entry that is hashed."""
    return {
        "id": str(entry.id),
        "tenant_id": str(entry.tenant_id),
        "seq": entry.seq,
        "occurred_at": format_timestamp(entry.occurred_at),
        "actor_id": str(entry.actor_id) if entry.actor_id else None,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "outcome": entry.outcome,
        "decision": entry.decision,
    }


class DatabaseAuditLog:
    """One linear chain per tenant.

    ``append`` runs in the caller's transaction: the entry is committed with the change
    it describes, or not at all. The chain head row is locked for the rest of that
    transaction, which is what puts concurrent writers of one tenant in order. SQLite
    has no row locks; there the engine opens every transaction as a write transaction,
    so writers queue on the database instead.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock if clock is not None else SystemClock()

    async def _locked_head(self, session: AsyncSession, tenant_id: UUID) -> AuditChainHead:
        query = (
            select(AuditChainHead)
            .where(AuditChainHead.tenant_id == tenant_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        head = await session.scalar(query)
        if head is not None:
            return head
        try:
            async with session.begin_nested():
                session.add(
                    AuditChainHead(
                        tenant_id=tenant_id, last_seq=0, last_hash=genesis_hash(tenant_id)
                    )
                )
        except IntegrityError:
            # Another transaction opened the chain first; its row is now visible.
            pass
        return (await session.scalars(query)).one()

    async def append(
        self, session: AsyncSession, tenant_id: UUID, record: AuditRecord
    ) -> AuditReceipt:
        head = await self._locked_head(session, tenant_id)
        entry = AuditEntry(
            id=new_id(),
            tenant_id=tenant_id,
            seq=head.last_seq + 1,
            occurred_at=self._clock.now(),
            actor_id=record.actor_id,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            outcome=record.outcome,
            decision=dict(record.decision) if record.decision is not None else None,
            prev_hash=head.last_hash,
        )
        entry.entry_hash = entry_hash(entry.prev_hash, entry_body(entry))
        session.add(entry)
        head.last_seq = entry.seq
        head.last_hash = entry.entry_hash
        await session.flush()
        return AuditReceipt(entry_id=entry.id, seq=entry.seq, entry_hash=entry.entry_hash)

    async def entries(
        self, session: AsyncSession, tenant_id: UUID, *, after_seq: int = 0, limit: int = 100
    ) -> Sequence[AuditEntry]:
        return (
            await session.scalars(
                select(AuditEntry)
                .where(AuditEntry.tenant_id == tenant_id, AuditEntry.seq > after_seq)
                .order_by(AuditEntry.seq)
                .limit(limit)
            )
        ).all()

    async def _stream(self, session: AsyncSession, tenant_id: UUID) -> AsyncIterator[AuditEntry]:
        after = 0
        while True:
            batch = await self.entries(session, tenant_id, after_seq=after, limit=500)
            for entry in batch:
                yield entry
            if len(batch) < 500:
                return
            after = batch[-1].seq

    async def _head(self, session: AsyncSession, tenant_id: UUID) -> tuple[int, str] | None:
        head = await session.scalar(
            select(AuditChainHead)
            .where(AuditChainHead.tenant_id == tenant_id)
            .execution_options(populate_existing=True)
        )
        return None if head is None else (head.last_seq, head.last_hash)

    async def verify(self, session: AsyncSession, tenant_id: UUID) -> VerificationReport:
        """Recompute the chain and report the first broken link, if any."""
        verifier = ChainVerifier(tenant_id)
        async for entry in self._stream(session, tenant_id):
            verifier.feed(entry_body(entry), entry.prev_hash, entry.entry_hash)
            if verifier.broken:
                break
        return verifier.finish(await self._head(session, tenant_id))

    async def export(self, session: AsyncSession, tenant_id: UUID) -> AsyncIterator[str]:
        """Yield the chain as JSON lines: a header, the entries, the head."""
        yield export_header(tenant_id, self._clock.now())
        seq, last_hash = 0, genesis_hash(tenant_id)
        async for entry in self._stream(session, tenant_id):
            yield export_entry(entry_body(entry), entry.prev_hash, entry.entry_hash)
            seq, last_hash = entry.seq, entry.entry_hash
        yield export_head(seq, last_hash)


def tenant_fail_mode(tenant: Tenant, default: FailMode) -> FailMode:
    """What happens to a request whose audit entry cannot be written.

    ``closed`` fails the request, ``open`` lets it through. A tenant setting overrides
    the deployment default (ADR-0017).
    """
    override = (tenant.settings or {}).get("audit", {}).get("fail_mode")
    return override if override in ("closed", "open") else default


async def set_tenant_fail_mode(
    session: AsyncSession,
    audit: DatabaseAuditLog,
    tenant: Tenant,
    mode: FailMode,
    *,
    actor_id: UUID | None,
) -> AuditReceipt:
    """Set the tenant's override. The change is itself an audit entry."""
    settings = dict(tenant.settings or {})
    settings["audit"] = {**settings.get("audit", {}), "fail_mode": mode}
    tenant.settings = settings
    return await audit.append(
        session,
        tenant.id,
        AuditRecord(
            action="audit.fail_mode.changed",
            outcome=mode,
            actor_id=actor_id,
            resource_type="tenant",
            resource_id=str(tenant.id),
        ),
    )
