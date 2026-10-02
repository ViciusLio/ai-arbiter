---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0028: Issue random API keys with a recognisable format and store an HMAC keyed with a pepper

## Context and Problem Statement

Applications authenticate to the gateway with an API key on every request. The key ties
the request to a tenant, a project, a principal and, optionally, an AI system. The check
runs on the request path, so it must be fast; the stored form must be useless to whoever
obtains the database; and a key must be revocable at once. The threat model of the audit
log (ADR-0017) already assumes an insider who can write to the database.

## Considered Options

- **A.** Random high-entropy key with a prefix and a key id, stored as a plain SHA-256
  digest.
- **B.** The same key, stored as HMAC-SHA-256 keyed with a server-side pepper that comes
  from the secret store.
- **C.** The same key, stored with a slow password hash (argon2).
- **D.** Signed stateless tokens, verified without a database read.

## Decision Outcome

Chosen option: **B**.

Format: `arb_<key id>_<secret><checksum>`

| Part | Content |
|---|---|
| `arb` | Fixed prefix, so that secret scanners and people recognise an Arbiter key |
| key id | 12 characters, lowercase letters and digits. Not secret: it identifies the key in lists, logs and audit entries, and is what the lookup uses |
| secret | 43 characters from `0-9A-Za-z`, drawn from the operating system's random source: slightly more than 256 bits |
| checksum | CRC-32 of everything before it, as 6 characters from the same alphabet. Lets a scanner or the gateway reject a mistyped or truncated key without a database read |

Storage and verification:

- The database holds the key id, `HMAC-SHA-256(pepper, key)` in hexadecimal and the id of
  the pepper that was used. The key itself is shown once, when it is issued.
- Verification parses the key, checks the checksum, reads the row by key id, recomputes
  the HMAC with the pepper named on the row and compares in constant time. A revoked or
  expired key is refused.
- The pepper is a secret reference in configuration, resolved through the `SecretStore`
  port. Several peppers can be configured, each with an id; one is active for new keys.
  Rotation adds a pepper and makes it active; existing keys keep verifying against the
  pepper they were issued with until they are reissued.
- A pepper shorter than 32 characters is refused at startup.
- `arbiter init` generates a pepper for the local workspace and writes it to `.env`,
  which git ignores; the environment secret store reads that file when the variable is
  not set in the environment. The quickstart needs no manual step.

### Consequences

- Good: a copy of the database does not reveal keys, and someone who can write to the
  database cannot insert a working key without the pepper.
- Good: verification costs one indexed read and one HMAC.
- Good: revocation is immediate, since every request reads the row.
- Bad: the pepper is one more secret to protect and back up. Losing it invalidates every
  key issued with it.
- Bad: one database read per request. A short-lived cache is possible later; it would
  delay revocation by its lifetime, so it is not added now.

## Pros and Cons of the Options

| Criterion | A. Plain SHA-256 | B. HMAC-SHA-256 with pepper | C. argon2 | D. Signed stateless tokens |
|---|---|---|---|---|
| Complexity | Low | Medium: pepper and its rotation | Medium | High |
| Azure cost | None | One secret in Key Vault | More CPU per replica | Signing keys in Key Vault |
| Scalability | Microseconds per request | Microseconds per request | Tens of milliseconds per request, or a cache | No database read |
| Security | A leak does not reveal keys; a database writer can insert a valid one | As A, and a database writer cannot forge a key | Protection meant for weak passwords, of no use with 256 random bits | No immediate revocation without a revocation list |
| Compliance / privacy | Immediate revocation | Immediate revocation | Immediate revocation | Delayed revocation, hard to defend in an audit |
| Maintainability | Minimal | Pepper rotation to operate | Native dependency | Signing key rotation, more code |
| Lock-in | None | None | None | None |

## More Information

- [Architecture overview](../architecture/README.md), section 6, threats to API keys
- [Data model](../architecture/data-model.md), `API_KEY`
