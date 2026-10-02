import asyncio
import json
from uuid import UUID

import pytest
from sqlalchemy import delete, select, update

from ai_arbiter.core.audit import (
    AuditChainHead,
    AuditEntry,
    AuditRecord,
    DatabaseAuditLog,
    genesis_hash,
    set_tenant_fail_mode,
    tenant_fail_mode,
    verify_export,
)
from ai_arbiter.core.domain.ids import new_id
from ai_arbiter.core.persistence.database import Database
from ai_arbiter.core.persistence.tenant import Tenant
from ai_arbiter.core.rules import Decision, DecisionKind


def record(number: int = 0) -> AuditRecord:
    return AuditRecord(
        action="chat.policy",
        outcome="allow",
        actor_id=new_id(),
        resource_type="interaction",
        resource_id=str(number),
        decision={"number": number, "note": "caffè €"},
    )


async def append_many(database: Database, tenant_id: UUID, count: int) -> None:
    audit = DatabaseAuditLog()
    for number in range(count):
        async with database.transaction() as session:
            await audit.append(session, tenant_id, record(number))


async def test_entries_are_numbered_and_linked(database: Database, tenant_id: UUID) -> None:
    audit = DatabaseAuditLog()
    async with database.transaction() as session:
        first = await audit.append(session, tenant_id, record(1))
        second = await audit.append(session, tenant_id, record(2))

    async with database.session() as session:
        entries = await audit.entries(session, tenant_id)

    assert (first.seq, second.seq) == (1, 2)
    assert entries[0].prev_hash == genesis_hash(tenant_id)
    assert entries[1].prev_hash == first.entry_hash
    assert entries[1].entry_hash == second.entry_hash
    assert first.entry_hash != second.entry_hash


async def test_a_sound_chain_verifies(database: Database, tenant_id: UUID) -> None:
    await append_many(database, tenant_id, 5)

    async with database.session() as session:
        report = await DatabaseAuditLog().verify(session, tenant_id)

    assert report.ok
    assert (report.entries, report.head_seq) == (5, 5)
    assert report.first_broken_seq is None


async def test_a_chain_with_no_entries_verifies(database: Database, tenant_id: UUID) -> None:
    async with database.session() as session:
        report = await DatabaseAuditLog().verify(session, tenant_id)

    assert report.ok
    assert (report.entries, report.head_hash) == (0, None)


async def test_a_changed_entry_is_detected_where_it_is(database: Database, tenant_id: UUID) -> None:
    await append_many(database, tenant_id, 5)
    async with database.transaction() as session:
        await session.execute(update(AuditEntry).where(AuditEntry.seq == 3).values(outcome="deny"))

    async with database.session() as session:
        report = await DatabaseAuditLog().verify(session, tenant_id)

    assert not report.ok
    assert report.first_broken_seq == 3
    assert report.problem == "entry hash does not match its content"
    assert report.entries == 2


async def test_a_changed_decision_is_detected(database: Database, tenant_id: UUID) -> None:
    await append_many(database, tenant_id, 3)
    async with database.transaction() as session:
        await session.execute(
            update(AuditEntry).where(AuditEntry.seq == 2).values(decision={"number": 99})
        )

    async with database.session() as session:
        report = await DatabaseAuditLog().verify(session, tenant_id)

    assert report.first_broken_seq == 2


async def test_a_removed_entry_is_detected(database: Database, tenant_id: UUID) -> None:
    await append_many(database, tenant_id, 5)
    async with database.transaction() as session:
        await session.execute(delete(AuditEntry).where(AuditEntry.seq == 2))

    async with database.session() as session:
        report = await DatabaseAuditLog().verify(session, tenant_id)

    assert not report.ok
    assert report.first_broken_seq == 2
    assert report.problem == "expected entry 2, found 3"


async def test_removing_the_last_entries_without_touching_the_head_is_detected(
    database: Database, tenant_id: UUID
) -> None:
    await append_many(database, tenant_id, 5)
    async with database.transaction() as session:
        await session.execute(delete(AuditEntry).where(AuditEntry.seq > 3))

    async with database.session() as session:
        report = await DatabaseAuditLog().verify(session, tenant_id)

    assert not report.ok
    assert report.first_broken_seq == 4
    assert report.problem == "the head says entry 5, the entries end at 3"


async def test_a_head_that_does_not_match_the_last_entry_is_detected(
    database: Database, tenant_id: UUID
) -> None:
    await append_many(database, tenant_id, 2)
    async with database.transaction() as session:
        await session.execute(update(AuditChainHead).values(last_hash="0" * 64))

    async with database.session() as session:
        report = await DatabaseAuditLog().verify(session, tenant_id)

    assert not report.ok
    assert report.problem == "the head hash does not match the last entry"


async def test_entries_without_a_head_are_detected(database: Database, tenant_id: UUID) -> None:
    await append_many(database, tenant_id, 2)
    async with database.transaction() as session:
        await session.execute(delete(AuditChainHead))

    async with database.session() as session:
        report = await DatabaseAuditLog().verify(session, tenant_id)

    assert not report.ok
    assert report.problem == "the chain has entries and no head"


async def test_concurrent_writers_produce_one_unbroken_chain(
    database: Database, tenant_id: UUID
) -> None:
    audit = DatabaseAuditLog()

    async def write(number: int) -> int:
        async with database.transaction() as session:
            return (await audit.append(session, tenant_id, record(number))).seq

    sequence_numbers = await asyncio.gather(*(write(number) for number in range(25)))

    assert sorted(sequence_numbers) == list(range(1, 26))
    async with database.session() as session:
        report = await audit.verify(session, tenant_id)
    assert report.ok
    assert report.entries == 25


async def test_each_tenant_has_its_own_chain(
    database: Database, tenant_id: UUID, other_tenant_id: UUID
) -> None:
    await append_many(database, tenant_id, 3)
    await append_many(database, other_tenant_id, 1)
    audit = DatabaseAuditLog()

    async with database.session() as session:
        mine = await audit.entries(session, tenant_id)
        theirs = await audit.entries(session, other_tenant_id)
        reports = [await audit.verify(session, t) for t in (tenant_id, other_tenant_id)]

    assert [entry.seq for entry in mine] == [1, 2, 3]
    assert [entry.seq for entry in theirs] == [1]
    assert theirs[0].prev_hash == genesis_hash(other_tenant_id) != genesis_hash(tenant_id)
    assert all(report.ok for report in reports)


async def test_an_entry_is_not_kept_when_its_transaction_rolls_back(
    database: Database, tenant_id: UUID
) -> None:
    audit = DatabaseAuditLog()
    await append_many(database, tenant_id, 1)

    async def failing() -> None:
        async with database.transaction() as session:
            await audit.append(session, tenant_id, record(2))
            raise RuntimeError("business change failed")

    with pytest.raises(RuntimeError):
        await failing()
    await append_many(database, tenant_id, 1)

    async with database.session() as session:
        entries = await audit.entries(session, tenant_id)
        report = await audit.verify(session, tenant_id)
    assert [entry.seq for entry in entries] == [1, 2]
    assert report.ok


async def test_entries_can_be_read_in_pages(database: Database, tenant_id: UUID) -> None:
    await append_many(database, tenant_id, 5)

    async with database.session() as session:
        page = await DatabaseAuditLog().entries(session, tenant_id, after_seq=2, limit=2)

    assert [entry.seq for entry in page] == [3, 4]


async def test_a_decision_is_stored_with_its_trace(database: Database, tenant_id: UUID) -> None:
    decision = Decision(kind=DecisionKind.POLICY, outcome="deny", input_digest="ab" * 32)
    async with database.transaction() as session:
        await DatabaseAuditLog().append(
            session,
            tenant_id,
            AuditRecord.of_decision(
                decision, action="chat.policy", resource_type="interaction", resource_id="i-1"
            ),
        )

    async with database.session() as session:
        stored = (await session.scalars(select(AuditEntry))).one()

    assert stored.outcome == "deny"
    assert stored.decision is not None
    assert stored.decision["id"] == str(decision.id)
    assert stored.decision["kind"] == "policy"


async def test_an_export_verifies_without_the_database(database: Database, tenant_id: UUID) -> None:
    await append_many(database, tenant_id, 4)

    async with database.session() as session:
        lines = [line async for line in DatabaseAuditLog().export(session, tenant_id)]

    header, head = json.loads(lines[0]), json.loads(lines[-1])
    assert header["type"] == "header"
    assert header["tenant_id"] == str(tenant_id)
    assert header["canonicalization"] == "RFC 8785"
    assert len(lines) == 6
    assert head == {"type": "head", "seq": 4, "hash": json.loads(lines[-2])["entry_hash"]}
    report = verify_export(lines)
    assert report.ok
    assert report.entries == 4


async def test_an_export_of_an_empty_chain_verifies(database: Database, tenant_id: UUID) -> None:
    async with database.session() as session:
        lines = [line async for line in DatabaseAuditLog().export(session, tenant_id)]

    assert len(lines) == 2
    assert verify_export(lines).ok


async def test_a_long_chain_is_read_in_batches(database: Database, tenant_id: UUID) -> None:
    audit = DatabaseAuditLog()
    async with database.transaction() as session:
        for number in range(501):
            await audit.append(session, tenant_id, AuditRecord(action="x", outcome=str(number)))

    async with database.session() as session:
        report = await audit.verify(session, tenant_id)

    assert report.ok
    assert report.entries == 501


async def test_fail_mode_defaults_to_the_deployment_and_can_be_overridden_per_tenant(
    database: Database, tenant_id: UUID
) -> None:
    audit = DatabaseAuditLog()
    actor = new_id()
    async with database.transaction() as session:
        tenant = await session.get_one(Tenant, tenant_id)
        before = tenant_fail_mode(tenant, "closed")
        await set_tenant_fail_mode(session, audit, tenant, "open", actor_id=actor)

    async with database.session() as session:
        tenant = await session.get_one(Tenant, tenant_id)
        entries = await audit.entries(session, tenant_id)

    assert before == "closed"
    assert tenant_fail_mode(tenant, "closed") == "open"
    assert [(e.action, e.outcome, e.actor_id) for e in entries] == [
        ("audit.fail_mode.changed", "open", actor)
    ]
