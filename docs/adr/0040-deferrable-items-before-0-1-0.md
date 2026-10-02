---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0040: Do the deferrable items of v0.1 before `0.1.0`, ahead of A2A and MCP

## Context and Problem Statement

ADR-0009 split v0.1 into a core and components that may follow in v0.1.x. The core is
done (Phases 3 and 4). The next step was either Phase 5 (A2A and MCP, v0.2) or the
deferrable components. The product's claim is that it compares what an organisation
declares with what its traffic shows; without importers and discovery that comparison
works only for traffic that goes through Arbiter's own gateway.

## Considered Options

- **1.** A phase for deferrable items before `0.1.0`: importers for LiteLLM and JSONL,
  discovery of systems from traffic, simulation scenarios, reports, e-mail delivery.
- **2.** Phase 5 (A2A and MCP) now; the deferrable items after.
- **3.** Only some deferrable items, named by the owner.

## Decision Outcome

Chosen option: **1**. The phase is called 4b.

In scope, in this order: the JSONL and LiteLLM importers (ADR-0019); system and audit
reports; delivery of the digest by e-mail; discovery of systems from traffic; simulation
scenarios. The last two open with their own decisions.

Not in this phase, still deferrable: post-call policy evaluation, external anchoring of
the audit head, the opt-in store of redacted content, further PII detectors, the local
agent, the remaining scanner rules.

Phase 5 (A2A and MCP) follows Phase 4b.

### Consequences

- Good: `0.1.0` can show declared against observed for traffic from another gateway.
- Good: the scenarios give a labelled set on which rules can be measured (I-13, I-27).
- Bad: A2A and MCP, which the roadmap promises for v0.2, start later.

## Pros and Cons of the Options

| Criterion | 1. Deferrable items first | 2. Phase 5 first | 3. A selection |
|---|---|---|---|
| Complexity | Medium: five items of known shape | High: two protocols to verify and design | Low to medium |
| Azure cost | None | None | None |
| Scalability | Not affected | Not affected | Not affected |
| Security | Imported data must be minimised on entry | A proxy in a new data path | Depends |
| Compliance / privacy | Undeclared use becomes visible, which the threat model names as the compensating signal | No change for v0.1 | Depends |
| Maintainability | Importers track third-party formats | SDKs of two moving protocols | Depends |
| Lock-in | None | On the protocol SDKs | None |

## More Information

- [ADR-0009](0009-v0-1-scope.md), [ADR-0019](0019-external-telemetry-ingestion.md)
- [Phase 4 summary](../phases/phase-4-compliance.md), open questions
