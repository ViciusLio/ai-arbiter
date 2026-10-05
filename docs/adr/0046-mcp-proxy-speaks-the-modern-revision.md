---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0046: The MCP proxy speaks the modern revision only

## Context and Problem Statement

MCP changed shape in revision `2026-07-28`: the core is stateless and every request stands on its own. Earlier revisions open a session with a handshake, and the two eras do not interoperate without an implementation that speaks both.

## Considered Options

- **1.** Modern only (`2026-07-28`)
- **2.** Dual-era on both sides, with translation
- **3.** Modern, plus pass-through of legacy to legacy without translation

## Decision Outcome

Chosen option: **1**.

The proxy accepts and forwards requests of revision `2026-07-28`. The catalogue records the revisions each server declares through `server/discover`; a server that offers only earlier revisions is listed as not governable by the proxy, and that is a finding.

### Consequences

- Good: one request is one decision; the proxy holds no session and scales as the gateway does.
- Bad: a legacy server or client is not served. Pass-through of the legacy era can be added later as its own decision.

## Pros and Cons of the Options

| Criterion | 1. Modern only (`2026-07-28`) | 2. Dual-era on both sides, with translation | 3. Modern, plus pass-through of legacy to legacy without translation |
|---|---|---|---|
| Complexity | Low: one request, one decision | High: sessions, and server-initiated requests turned into multi round-trip ones | Medium: a second, stateful path |
| Azure cost | None | None | None |
| Scalability | Stateless, any number of replicas | Session affinity | Session affinity for the legacy path |
| Security | One path to reason about | The largest surface | Two paths |
| Compliance / privacy | Every call is seen and audited | The same | The same |
| Maintainability | Follows the current revision | Follows two eras and their mapping | Follows two eras |
| Lock-in | None | None | None |

## More Information

- [Phase 5 preparation](../phases/phase-5-preparation.md), decision P5-1: what was
  read on the official sources, and where
