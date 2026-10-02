---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0002 — Position Arbiter as compliance-first, with its own lean gateway

## Context and Problem Statement

Mature open source gateways (LiteLLM, Kong AI Gateway, Portkey, agentgateway) already
cover LLM routing, budgets, guardrails and MCP; some cover A2A. None of them ties live
traffic to an inventory of AI systems classified under the EU AI Act. The brief lists
fifteen modules across two products; without a clear centre of gravity the result would
be broad and shallow.

## Considered Options

- **A.** Compliance-first: a lean gateway of our own, differentiated by the bridge between
  traffic and AI Act classification.
- **B.** Gateway-first: chase feature parity, compliance as an add-on.
- **C.** Toolkit only, shipped as a plugin of an existing gateway.

## Decision Outcome

Chosen option: **A**, with two binding constraints set by the project owner:

1. **A2A and MCP stay explicitly on the roadmap for v0.2.** They are deferred, not dropped.
2. **The compliance toolkit must be able to ingest data from external gateways**
   (LiteLLM, Azure API Management) through adapters. The toolkit must not require
   Arbiter's own gateway. See [ADR-0019](0019-external-telemetry-ingestion.md).

### Consequences

- Good: every skill in the brief is demonstrated without a feature race against mature
  products.
- Good: constraint 2 makes the toolkit useful to teams that already run another gateway.
- Bad: the gateway will support few providers; this is stated openly in the README.
- Follow-up: gateway and compliance must not import each other; both depend on contracts
  in the shared core ([ADR-0010](0010-single-distribution-with-enforced-boundaries.md)).

## Pros and Cons of the Options

| Criterion | A. Compliance-first | B. Gateway-first | C. Toolkit as plugin |
|---|---|---|---|
| Complexity | Medium | High | Low |
| Azure cost | Low (one app + PostgreSQL) | Medium | Minimal |
| Scalability | Adequate (stateless async proxy) | Needs serious data-path tuning | Delegated to the host gateway |
| Security | Small surface, under direct control | Large surface | Inherited from the host |
| Compliance / privacy | First-hand evidence; full control of redaction and audit | Same, with less time spent on it | Limited to what the host exposes |
| Maintainability | Sustainable for one person | Not sustainable | Depends on third-party APIs |
| Lock-in | None | None | On the host gateway |
| Portfolio value | High | Low (clone) | Medium (no routing, A2A or MCP) |

## More Information

- [Phase 0 analysis](../phases/phase-0-analysis.md), sections 2.3 and 8 (D1)
