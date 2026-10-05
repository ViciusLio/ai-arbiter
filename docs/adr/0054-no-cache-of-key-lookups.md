---
status: accepted
date: 2026-10-05
decision-makers: Project owner (delegated to the implementer, with security and compliance as the first criteria)
---

# 0054: API keys and roles are read on every request; they are not cached

## Context and Problem Statement

Every request authenticates its API key against the database: the key row, its project
and the role bindings of its principal, three statements of the roughly seventeen a
request makes (I-15, I-20). A cache with a short lifetime would remove them.

What a cache holds is exactly what an operator changes in an emergency: whether a key is
revoked, whether it has expired, which roles its principal has, which AI system it is
tied to. The owner asked for the strategy to be chosen with security and compliance
first.

## Considered Options

- **1.** No cache: every request reads the key, the project and the roles.
- **2.** A cache in each process with a short lifetime, for example thirty seconds.
- **3.** A cache invalidated by an event when a key or a role changes.

## Decision Outcome

Chosen option: **1**.

- A revoked or expired key stops working at the next request, in every process, with
  nothing to wait for and nothing to flush. The same holds for a role that is taken
  away and for a key tied to a system that was just classified as a prohibited practice.
- The audit log can state when a key was revoked and be believed: no request is
  accepted after that entry.
- The cost stays where it is measured. The latency of the request path is reduced
  elsewhere (I-15: one statement for the roll-ups, one audit entry per request), where
  no security property is traded.

### Consequences

- Good: revocation is immediate and needs no explanation in an incident.
- Good: no secret-derived state is held in memory beyond one request.
- Bad: three statements per request remain. On PostgreSQL they are indexed reads.
- Revisit only with a measurement that shows these reads to be the bottleneck, and then
  with option 3, never option 2 alone.

## Pros and Cons of the Options

| Criterion | 1. No cache | 2. Short lifetime | 3. Invalidated by events |
|---|---|---|---|
| Complexity | None | Low | High: the bus is in-process today, so several processes would not hear each other |
| Azure cost | None | None | A broker, once there are several replicas |
| Scalability | Three indexed reads per request | Fewer reads | Fewer reads |
| Security | Revocation and role changes are immediate | A revoked key works until the entry expires, in every process that cached it | Immediate when the event arrives; a lost event leaves a revoked key working |
| Compliance / privacy | The audit entry of a revocation is the moment access ended | Access continues after the recorded moment | As 1 when delivery is reliable |
| Maintainability | Nothing to maintain | A lifetime to choose and defend | Invalidation paths for keys, roles, projects and systems |
| Lock-in | None | None | On the bus |

## More Information

- [ADR-0028](0028-api-keys-hmac-with-pepper.md),
  [ADR-0017](0017-audit-hash-chain-per-tenant.md); improvements I-15 and I-20 in the README
