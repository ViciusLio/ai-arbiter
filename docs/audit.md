# The audit log

Every automated outcome and every administrative change is written to an append-only log,
one chain per tenant (ADR-0017). This page describes the chain precisely enough to verify
an export with tools of your own.

> Arbiter is a support tool. It does not provide legal advice.

## What an entry holds

| Field | Content |
|---|---|
| `id` | Identifier of the entry (UUIDv7) |
| `tenant_id` | The tenant the chain belongs to |
| `seq` | Position in the chain, from 1, without gaps |
| `occurred_at` | UTC timestamp, `YYYY-MM-DDTHH:MM:SS.ffffffZ` |
| `actor_id` | Principal that caused the entry, or null |
| `action` | What happened: `chat.policy`, `chat.routing`, `api_key.issued`, `budget.created`, `audit.fail_mode.changed`, ... |
| `resource_type`, `resource_id` | What it happened to, by identifier |
| `outcome` | `allow`, `deny`, `redact`, `route:<deployment>`, `failed`, `no_route`, `ok`, ... |
| `decision` | For automated outcomes, the decision envelope: rule ids and versions, the conditions that matched, legal references, a digest of the facts. Otherwise null |
| `prev_hash`, `entry_hash` | The links of the chain |

An entry never holds prompt or completion text, and never a name: principals, teams and
projects appear by identifier. Erasing a person's name from `principal` leaves the chain
intact.

## How the chain is computed

```text
genesis    = SHA-256( JCS({"chain": "ai-arbiter-audit", "tenant_id": "<uuid>", "version": 1}) )
entry_hash = SHA-256( bytes(prev_hash) || JCS(body) )
```

- `JCS` is canonical JSON as defined by RFC 8785. Entries contain no floating-point
  numbers (ADR-0029).
- `body` is the entry with the ten fields of the table above except the two hashes.
- `prev_hash` is the `entry_hash` of the previous entry, or `genesis` for the first one.
  `bytes(prev_hash)` are its 32 raw bytes, not its hexadecimal text.

## Verifying

```bash
arbiter audit verify                      # the chain in the database
arbiter audit export -o audit.jsonl       # header, one line per entry, head
arbiter audit verify --file audit.jsonl   # the file, with no database
```

The same is available over HTTP: `GET /api/v1/audit/verify` and `GET /api/v1/audit/export`.

Verification reports the first broken link: an entry whose content no longer matches its
hash, a missing or reordered entry, a head that does not match the last entry.

### With your own tools

An export is a text file with one JSON object per line: a `header`, the `entry` lines in
order, and a `head` with the last sequence number and hash. This is a complete verifier
in Python, using an independent RFC 8785 library (`pip install rfc8785`):

```python
import hashlib
import json
import sys

import rfc8785

BODY = (
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

lines = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
header, entries, head = lines[0], lines[1:-1], lines[-1]
genesis = {"chain": "ai-arbiter-audit", "tenant_id": header["tenant_id"], "version": 1}
previous = hashlib.sha256(rfc8785.dumps(genesis)).hexdigest()
for number, entry in enumerate(entries, start=1):
    body = {name: entry[name] for name in BODY}
    computed = hashlib.sha256(bytes.fromhex(previous) + rfc8785.dumps(body)).hexdigest()
    assert entry["seq"] == number, f"entry {number} is missing"
    assert entry["prev_hash"] == previous, f"entry {number} does not follow the one before"
    assert entry["entry_hash"] == computed, f"entry {number} was changed"
    previous = computed
assert (head["seq"], head["hash"]) == (len(entries), previous), "the head does not match"
print(f"{len(entries)} entries, no broken link")
```

The test suite of Arbiter runs this computation against the `rfc8785` library on every
build.

## What verification proves, and what it does not

The chain is **tamper-evident, not tamper-proof**.

- A change to an entry, or the removal of an entry in the middle, breaks the chain from
  that point and is detected.
- Someone who can write to the database can rewrite the **whole** chain, or drop the last
  entries and move the head back, and produce a chain that verifies. The chain alone
  cannot detect that.
- The defence is to keep a copy of the head outside the database: an export stored
  elsewhere, or the head hash printed by `arbiter audit verify` and recorded somewhere
  the database administrator cannot change. Periodic anchoring to an external
  destination is planned for v0.1.x, and signed checkpoints for the Azure release
  (ADR-0017).

## When the log cannot be written

A request and its audit entries are written in one transaction. If that transaction
fails, `audit.fail_mode` decides:

| Mode | Effect |
|---|---|
| `closed` (default) | The request fails with 503. Nothing is answered that is not recorded |
| `open` | The request is answered and the failure is logged |

The deployment default is `audit.fail_mode` in the configuration. A tenant can override
it with `PUT /api/v1/audit/fail-mode`; the change is itself an audit entry.

Two limits follow from how responses are produced:

- A streamed response is recorded when the stream ends. By then the client has received
  it, so a failed write cannot fail the request, whatever the mode. It is logged.
- A request denied by policy is denied even if the denial cannot be recorded.
