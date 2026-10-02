import hashlib
import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import rfc8785

from ai_arbiter.core.audit.chain import (
    ChainVerifier,
    entry_hash,
    export_entry,
    export_head,
    export_header,
    format_timestamp,
    genesis_hash,
    verify_export,
)

TENANT = UUID("018f0000-0000-7000-8000-000000000001")
NOW = datetime(2026, 10, 2, 12, 0, 0, 5, tzinfo=UTC)


def body(seq: int, outcome: str = "allow") -> dict[str, object]:
    return {
        "id": f"018f0000-0000-7000-8000-0000000001{seq:02d}",
        "tenant_id": str(TENANT),
        "seq": seq,
        "occurred_at": format_timestamp(NOW),
        "actor_id": None,
        "action": "chat.policy",
        "resource_type": "interaction",
        "resource_id": "abc",
        "outcome": outcome,
        "decision": {"kind": "policy", "matches": []},
    }


def export(count: int) -> list[str]:
    lines = [export_header(TENANT, NOW)]
    previous = genesis_hash(TENANT)
    for seq in range(1, count + 1):
        current = entry_hash(previous, body(seq))
        lines.append(export_entry(body(seq), previous, current))
        previous = current
    lines.append(export_head(count, previous))
    return lines


def test_the_hash_can_be_recomputed_with_an_independent_canonicaliser() -> None:
    """What a third party does to check an entry, with a library of their choice."""
    genesis = hashlib.sha256(
        rfc8785.dumps({"chain": "ai-arbiter-audit", "tenant_id": str(TENANT), "version": 1})
    ).hexdigest()
    expected = hashlib.sha256(bytes.fromhex(genesis) + rfc8785.dumps(body(1))).hexdigest()  # type: ignore[arg-type]

    assert genesis_hash(TENANT) == genesis
    assert entry_hash(genesis, body(1)) == expected


def test_timestamps_are_written_in_utc_with_a_fixed_width() -> None:
    rome = timezone(timedelta(hours=2))

    assert format_timestamp(NOW) == "2026-10-02T12:00:00.000005Z"
    assert format_timestamp(datetime(2026, 10, 2, 14, 0, tzinfo=rome)) == (
        "2026-10-02T12:00:00.000000Z"
    )


def test_a_sound_export_verifies() -> None:
    report = verify_export(export(3))

    assert report.ok
    assert (report.entries, report.head_seq) == (3, 3)


def test_blank_lines_in_an_export_are_ignored() -> None:
    lines = export(2)

    assert verify_export([lines[0], "", *lines[1:], "  "]).ok


def test_an_edited_line_is_detected() -> None:
    lines = export(3)
    edited = json.loads(lines[2])
    edited["outcome"] = "deny"
    lines[2] = json.dumps(edited)

    report = verify_export(lines)

    assert not report.ok
    assert report.first_broken_seq == 2
    assert report.entries == 1


def test_a_removed_line_is_detected() -> None:
    lines = export(3)
    del lines[2]

    assert verify_export(lines).first_broken_seq == 2


def test_reordered_lines_are_detected() -> None:
    lines = export(3)
    lines[1], lines[2] = lines[2], lines[1]

    assert verify_export(lines).first_broken_seq == 1


def test_a_truncated_export_is_detected() -> None:
    report = verify_export(export(3)[:-1])

    assert not report.ok
    assert report.problem == "the file has no head line: it may be truncated"


def test_an_export_cut_before_the_last_entry_but_with_the_head_is_detected() -> None:
    lines = export(3)
    del lines[3]

    report = verify_export(lines)

    assert not report.ok
    assert report.problem == "the head says entry 3, the entries end at 2"


def test_an_entry_of_another_tenant_is_detected() -> None:
    lines = export(1)
    foreign = json.loads(lines[1])
    foreign["tenant_id"] = "018f0000-0000-7000-8000-000000000002"
    lines[1] = json.dumps(foreign)

    assert verify_export(lines).problem == "entry belongs to another tenant"


def test_files_that_are_not_exports_are_rejected() -> None:
    header = export(0)[0]

    assert verify_export([]).problem == "the file is empty"
    assert verify_export(["not json"]).problem == "line 1 is not JSON"
    assert verify_export(['{"type":"entry"}']).problem == (
        "the file does not start with an export header"
    )
    assert verify_export([header.replace('"version":1', '"version":2')]).problem == (
        "unsupported export version 2"
    )
    assert verify_export(
        ['{"type":"header","format":"ai-arbiter-audit-export","version":1}']
    ).problem == ("the header has no valid tenant id")
    assert verify_export([header, '{"type":"other"}']).problem == "line 2 has an unknown type"
    assert verify_export([*export(1), export(1)[1]]).problem == "line 4 comes after the head"


def test_a_float_in_an_entry_breaks_verification_instead_of_crashing() -> None:
    verifier = ChainVerifier(TENANT)
    broken = {**body(1), "decision": {"score": 0.5}}

    verifier.feed(broken, genesis_hash(TENANT), "0" * 64)

    assert verifier.finish((1, "0" * 64)).problem == "entry cannot be canonicalised"
