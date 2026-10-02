---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0008 — Develop locally only until Phase 6; estimate costs and set budget alerts then

## Context and Problem Statement

Azure is the target cloud, but nothing in Phases 1–5 needs a live subscription if every
Azure service sits behind an adapter with a local substitute. Spending before the system
is worth deploying adds cost and no information.

## Considered Options

- **A.** Local development only until Phase 6.
- **B.** Deploy a minimal Azure environment early and keep it running.

## Decision Outcome

Chosen option: **A**.

- Phases 1–5 run on Docker Compose with local substitutes. No Azure resource is created.
- Phase 6 opens with a cost estimate for the demo environment and configures budget
  alerts on the subscription before anything else is deployed.

### Consequences

- Good: zero cloud cost until Phase 6.
- Bad: Azure-specific problems (managed identity, networking, cold starts) surface late.
  Mitigation: adapters are written against the official SDK contracts and covered by
  contract tests with recorded responses.
- Exception: the Azure OpenAI adapter can be exercised earlier against an existing
  deployment if the project owner provides one; it is never required by the test suite.

## Open

The project owner has not yet stated whether a subscription exists and what monthly
budget is acceptable. This is not blocking before Phase 6.

## Pros and Cons of the Options

| Criterion | A. Local until Phase 6 | B. Early Azure environment |
|---|---|---|
| Azure cost | None until Phase 6 | Recurring from Phase 2 |
| Complexity | Low | Infrastructure work competes with the MVP |
| Risk discovery | Late for Azure specifics | Early |
| Lock-in | Forces real adapter boundaries | Tempts direct SDK use |

## More Information

- [Phase 0 analysis](../phases/phase-0-analysis.md), section 8 (D7)
