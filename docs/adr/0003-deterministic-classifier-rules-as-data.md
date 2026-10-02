---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0003: Classify deterministically, with rules as versioned data

## Context and Problem Statement

AI Act classification depends on the intended purpose of a system, which cannot be
inferred from traffic. The brief requires every automated decision to be explainable and
the CLI to work offline. Application dates also changed in July 2026 and will change
again, so every result must state which version of the law it reflects.

## Considered Options

- **A.** Deterministic decision logic over declared attributes; gateway traffic supplies
  evidence and inconsistencies.
- **B.** LLM-first classification from a free-text description.
- **C.** Hybrid: deterministic logic decides; an opt-in LLM only suggests attribute values.

## Decision Outcome

Chosen option: **A** for v0.1, designed so that **C** can be added later.

Binding constraints set by the project owner:

1. **Rules are versioned data**, not code. Each rule carries the article it implements
   and the regulatory version it was written against.
2. **An LLM may suggest, never decide.** Any future LLM assistance proposes attribute
   values that a human confirms; the classification itself always comes from the rules.

### Consequences

- Good: the same input and rule pack always give the same output, with a trace of which
  conditions matched.
- Good: works offline and sends nothing to a model.
- Bad: rule packs must be maintained by hand when the law or guidance changes.
- Bad: quality depends on the honesty and completeness of declared attributes; the output
  is labelled "indicative".
- Follow-up: rule pack format and engine in
  [ADR-0012](0012-unified-declarative-rule-engine.md).

## Pros and Cons of the Options

| Criterion | A. Deterministic | B. LLM-first | C. Hybrid |
|---|---|---|---|
| Complexity | Medium | Low at first, high to make reliable | High |
| Azure cost | None | Tokens per classification | Tokens only when enabled |
| Scalability | Excellent | Bounded by quota and latency | Excellent |
| Security | No data leaves the process | System descriptions sent to a model | Explicit opt-in |
| Compliance / privacy | Explainable, reproducible, offline | Not reproducible; hard to defend in an audit | Explainable; suggestions marked as such |
| Maintainability | Rules updated by hand | Fragile prompts | Both |
| Lock-in | None | On the model | None |

## More Information

- [Phase 0 analysis](../phases/phase-0-analysis.md), sections 2.1 and 8 (D2)
