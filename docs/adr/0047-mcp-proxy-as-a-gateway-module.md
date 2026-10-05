---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0047: The MCP proxy is a module of the gateway application, switched on by a role

## Context and Problem Statement

A proxy that authorises and logs MCP calls needs identity, policy, the audit chain and the database. The gateway application already wires them (ADR-0020 defines the roles a server process can take).

## Considered Options

- **1.** A module of the gateway application, switched on by a server role
- **2.** A separate application in the same distribution
- **3.** A separate distribution

## Decision Outcome

Chosen option: **1**.

The proxy lives in `gateway`, is served by the same application and is enabled by a server role, so that it can also run on its own.

### Consequences

- Good: one authentication path and one audit chain per tenant.
- Bad: the gateway package grows; the import rules keep the proxy from reaching into the compliance toolkit.

## Pros and Cons of the Options

| Criterion | 1. A module of the gateway application, switched on by a server role | 2. A separate application in the same distribution | 3. A separate distribution |
|---|---|---|---|
| Complexity | Low: identity, policy, audit and the database are already there | Medium: a second composition root | High |
| Azure cost | None | None | None |
| Scalability | Scales with the gateway; the role lets it run alone when needed (ADR-0020) | Independent | Independent |
| Security | One authentication path | Two to keep equal | Two |
| Compliance / privacy | One audit chain per tenant | The same, across processes | The same |
| Maintainability | Good | Duplicated wiring | Two releases |
| Lock-in | None | None | None |

## More Information

- [Phase 5 preparation](../phases/phase-5-preparation.md), decision P5-2: what was
  read on the official sources, and where
