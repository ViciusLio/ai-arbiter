---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0017 — Chain audit entries per tenant with SHA-256 over canonical JSON

## Context and Problem Statement

The brief requires an append-only audit log with a hash chain, verifiable and exportable.
Three problems follow: concurrent writers must agree on the order of entries; an
append-only log conflicts with erasure and retention duties; and whoever can write to the
database can rewrite the whole chain, so integrity is only as strong as its anchor.

## Considered Options

- **A.** One linear chain per tenant; the chain head is locked for the duration of the
  append; entries hashed with SHA-256 over RFC 8785 canonical JSON.
- **B.** Entries inserted unchained; a background sealer assigns sequence numbers and
  hashes in batches.
- **C.** Merkle-tree transparency log.

## Decision Outcome

Chosen option: **A** for v0.1. **B** is the documented path if a single tenant's write
rate outgrows it. Signed checkpoints are added in Phase 6.

- `entry_hash = SHA-256(prev_hash ‖ JCS(entry))`, with a per-tenant genesis entry.
- The append takes a row lock on `audit_chain_head` (PostgreSQL) or relies on SQLite's
  single writer, inside the same transaction as the business change.
- **No personal data content in audit entries.** Entries hold action, outcome, rule
  references, resource ids and pseudonymous actor ids. Erasure removes the mapping from
  pseudonym to person and leaves the chain intact.
- `arbiter audit verify` recomputes the chain and reports the first broken link.
  Exports are JSONL with the head hash, so a copy can be verified elsewhere.
- `audit.fail_mode` is `closed` by default: if the audit entry cannot be written, the
  request fails. **It is configurable per tenant** (changed at acceptance): a tenant
  setting overrides the deployment default, and the change of mode is itself audited.
- **External anchoring before Phase 6** (added at acceptance). The head of each chain
  (tenant, sequence number, hash, timestamp) is written periodically to a destination
  outside the database through an `AnchorSink` port, so that a complete rewrite of a
  chain becomes detectable: the rewritten chain no longer matches the anchors.
  `arbiter audit verify` checks the chain against the anchors it is given.
  Sinks delivered with the audit module in Phase 3: an append-only file on a separate
  volume, and a structured log line that leaves through the logging pipeline. From
  Phase 4 the daily digest also prints the head, which puts a copy in the hands of its
  recipients.
- Phase 6: the anchors become signed checkpoints, through a `Signer` port (Azure Key
  Vault), stored on immutable storage.

### Consequences

- Good: tampering with any entry is detectable from that point onward.
- Good: with anchoring, a full rewrite is detectable back to the last anchor that the
  attacker could not also alter.
- Bad: anchors are only as trustworthy as their destination. Someone who controls both
  the database and every anchor sink can still rewrite history undetected until Phase 6;
  the documentation says "tamper-evident", not "tamper-proof".
- Bad: entries written after the latest anchor are protected only by the chain itself;
  the anchoring interval is the exposure window and is configurable.
- Bad: appends for one tenant are serialised; this caps the write rate per tenant.
- Bad: `fail_mode: closed` turns a database outage into a gateway outage. That is the
  intended default for a compliance tool and can be changed per deployment.

## Pros and Cons of the Options

| Criterion | A. Linear chain, locked head | B. Batch sealer | C. Merkle log |
|---|---|---|---|
| Complexity | Low | Medium | High |
| Azure cost | None | None | Extra service or storage |
| Scalability | Hundreds of appends per second per tenant | Thousands | Very high |
| Security | Detects partial tampering; needs external anchor | Same, with a window of unsealed entries | Inclusion and consistency proofs |
| Compliance / privacy | Entry is chained before the response is sent | Entry exists but is not yet protected | Strongest evidence |
| Maintainability | Simple to verify and explain | Sealer to operate and monitor | Specialised |
| Lock-in | None | None | Depends on the implementation |

## More Information

- [Phase 0 analysis](../phases/phase-0-analysis.md), items A13, A14 and risk R12
- [RFC 8785 — JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785)
