"""The arithmetic of the audit chain, with no database in sight.

Everything needed to recompute a chain from an export is in this module, so that the
verification of a file and the verification of the database share one definition.

    genesis    = SHA-256(JCS({"chain": "ai-arbiter-audit", "tenant_id": ..., "version": 1}))
    entry_hash = SHA-256(bytes(prev_hash) || JCS(body))

``JCS`` is RFC 8785 canonical JSON, ``prev_hash`` is the hash of the previous entry (the
genesis hash for the first one) and ``body`` is the entry without its two hashes.
"""

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ai_arbiter.core.canonical_json import CanonicalizationError, canonicalize, sha256_hex

CHAIN_NAME = "ai-arbiter-audit"
CHAIN_VERSION = 1
EXPORT_FORMAT = "ai-arbiter-audit-export"

BODY_FIELDS = (
    "id",
    "tenant_id",
    "seq",
    "occurred_at",
    "actor_id",
    "action",
    "resource_type",
    "resource_id",
    "outcome",
    "decision",
)


def genesis_hash(tenant_id: UUID) -> str:
    return sha256_hex({"chain": CHAIN_NAME, "tenant_id": str(tenant_id), "version": CHAIN_VERSION})


def format_timestamp(value: datetime) -> str:
    """RFC 3339 in UTC with microseconds, always the same width."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def entry_hash(prev_hash: str, body: Mapping[str, Any]) -> str:
    return hashlib.sha256(bytes.fromhex(prev_hash) + canonicalize(body)).hexdigest()


@dataclass(frozen=True)
class VerificationReport:
    ok: bool
    entries: int
    head_seq: int
    head_hash: str | None
    first_broken_seq: int | None = None
    problem: str | None = None


class ChainVerifier:
    """Checks entries one at a time, in order. Stops at the first broken link."""

    def __init__(self, tenant_id: UUID) -> None:
        self._expected_prev = genesis_hash(tenant_id)
        self._tenant_id = str(tenant_id)
        self._seq = 0
        self._broken: tuple[int, str] | None = None

    @property
    def broken(self) -> bool:
        return self._broken is not None

    def feed(self, body: Mapping[str, Any], prev_hash: str, stored_hash: str) -> None:
        if self._broken is not None:
            return
        seq = body.get("seq")
        expected_seq = self._seq + 1
        if seq != expected_seq:
            self._broken = (expected_seq, f"expected entry {expected_seq}, found {seq}")
            return
        if body.get("tenant_id") != self._tenant_id:
            self._broken = (expected_seq, "entry belongs to another tenant")
            return
        if prev_hash != self._expected_prev:
            self._broken = (expected_seq, "previous hash does not match the entry before")
            return
        try:
            computed = entry_hash(prev_hash, body)
        except (CanonicalizationError, ValueError):
            self._broken = (expected_seq, "entry cannot be canonicalised")
            return
        if computed != stored_hash:
            self._broken = (expected_seq, "entry hash does not match its content")
            return
        self._seq = expected_seq
        self._expected_prev = stored_hash

    def finish(self, head: tuple[int, str] | None) -> VerificationReport:
        """Close the check against the recorded chain head.

        ``None`` means no head is recorded, which is sound only for a chain that has no
        entries either.
        """
        if self._broken is None:
            if head is None:
                if self._seq:
                    self._broken = (self._seq + 1, "the chain has entries and no head")
            elif head[0] != self._seq:
                self._broken = (
                    min(head[0], self._seq) + 1,
                    f"the head says entry {head[0]}, the entries end at {self._seq}",
                )
            elif head[1] != self._expected_prev:
                self._broken = (self._seq + 1, "the head hash does not match the last entry")
        return VerificationReport(
            ok=self._broken is None,
            entries=self._seq,
            head_seq=self._seq,
            head_hash=self._expected_prev if self._seq else None,
            first_broken_seq=self._broken[0] if self._broken else None,
            problem=self._broken[1] if self._broken else None,
        )


def export_header(tenant_id: UUID, exported_at: datetime) -> str:
    return canonicalize(
        {
            "type": "header",
            "format": EXPORT_FORMAT,
            "version": CHAIN_VERSION,
            "tenant_id": str(tenant_id),
            "genesis_hash": genesis_hash(tenant_id),
            "hash_algorithm": "sha256",
            "canonicalization": "RFC 8785",
            "exported_at": format_timestamp(exported_at),
        }
    ).decode("utf-8")


def export_entry(body: Mapping[str, Any], prev_hash: str, stored_hash: str) -> str:
    return canonicalize(
        {"type": "entry", **body, "prev_hash": prev_hash, "entry_hash": stored_hash}
    ).decode("utf-8")


def export_head(seq: int, head_hash: str) -> str:
    return canonicalize({"type": "head", "seq": seq, "hash": head_hash}).decode("utf-8")


def _invalid(problem: str) -> VerificationReport:
    return VerificationReport(
        ok=False, entries=0, head_seq=0, head_hash=None, first_broken_seq=1, problem=problem
    )


def verify_export(lines: Iterable[str]) -> VerificationReport:
    """Verify an export file: header, entries in order, head. Needs no database."""
    verifier: ChainVerifier | None = None
    head: tuple[int, str] | None = None
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return _invalid(f"line {number} is not JSON")
        kind = record.get("type") if isinstance(record, dict) else None
        if verifier is None:
            if kind != "header" or record.get("format") != EXPORT_FORMAT:
                return _invalid("the file does not start with an export header")
            if record.get("version") != CHAIN_VERSION:
                return _invalid(f"unsupported export version {record.get('version')}")
            try:
                verifier = ChainVerifier(UUID(str(record.get("tenant_id"))))
            except ValueError:
                return _invalid("the header has no valid tenant id")
        elif head is not None:
            return _invalid(f"line {number} comes after the head")
        elif kind == "entry":
            body = {field: record.get(field) for field in BODY_FIELDS}
            verifier.feed(body, str(record.get("prev_hash")), str(record.get("entry_hash")))
        elif kind == "head":
            seq = record.get("seq")
            head = (seq if isinstance(seq, int) else -1, str(record.get("hash")))
        else:
            return _invalid(f"line {number} has an unknown type")
    if verifier is None:
        return _invalid("the file is empty")
    if head is None and not verifier.broken:
        report = verifier.finish((0, ""))
        return VerificationReport(
            ok=False,
            entries=report.entries,
            head_seq=report.head_seq,
            head_hash=report.head_hash,
            first_broken_seq=report.head_seq + 1,
            problem="the file has no head line: it may be truncated",
        )
    return verifier.finish(head)
