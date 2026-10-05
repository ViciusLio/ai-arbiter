---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0051: For A2A: a registry of agents with verified cards, then authorization and a proxy for the JSON-RPC and HTTP+JSON bindings

## Context and Problem Statement

The brief asks for A2A with a registry of agents. A2A 1.0 has three bindings; an agent publishes a card that says which it offers.

## Considered Options

- **1.** A registry of agents with verified cards, and findings
- **2.** As 1, plus authorization and a proxy for the JSON-RPC and HTTP+JSON bindings, with an audit entry per call
- **3.** As 2, plus gRPC

## Decision Outcome

Chosen option: **2**.

In two steps. First a registry: cards are fetched, stored, verified and tied to declared AI systems, with findings. Then authorization and a proxy for the JSON-RPC and HTTP+JSON bindings, with one audit entry per call. gRPC is not proxied: an agent that offers only gRPC is listed as not governable.

### Consequences

- Good: the registry is useful on its own and is delivered first.
- Bad: gRPC traffic stays invisible; streaming and task subscriptions make the proxy the largest item of the phase.

## Pros and Cons of the Options

| Criterion | 1. A registry of agents with verified cards, and findings | 2. As 1, plus authorization and a proxy for the JSON-RPC and HTTP+JSON bindings, with an audit entry per call | 3. As 2, plus gRPC |
|---|---|---|---|
| Complexity | Low to medium | High: streaming and task subscriptions | Very high |
| Azure cost | None | None | None |
| Scalability | Not in the data path | A second proxied protocol | The same |
| Security | Cards are checked; calls are not seen | Calls are authorized | The same |
| Compliance / privacy | Declared agents; undeclared use is invisible | Declared against observed | The same |
| Maintainability | Good | Follows the SDK | A third binding |
| Lock-in | None | On the SDK | On the SDK |

## More Information

- [Phase 5 preparation](../phases/phase-5-preparation.md), decision P5-6: what was
  read on the official sources, and where
