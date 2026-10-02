---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0006 — Ship no web UI in v0.1; make HTML outputs and OpenAPI docs the visible surface

## Context and Problem Statement

The brief does not mention a web interface. A single-page application would add a second
toolchain and a large share of the effort, while the project still needs something a
visitor can look at.

## Considered Options

- **A.** No SPA in v0.1. API, CLI, static HTML digests and reports.
- **B.** A read-only dashboard in v0.1.

## Decision Outcome

Chosen option: **A**, with the project owner's requirement that the **HTML digest and
reports be well designed** and that the **OpenAPI documentation be treated as a product
surface**.

Concretely:

- Digest and report HTML are self-contained files (inline CSS, no external requests),
  readable on mobile and printable.
- The OpenAPI schema has tags per module, summaries, descriptions, typed error responses
  and request/response examples for every endpoint.

A dashboard can be reconsidered after v0.1 through a new ADR.

### Consequences

- Good: one toolchain; effort goes into the engine.
- Good: self-contained HTML files work offline and can be attached to an email.
- Bad: no interactive exploration of findings; the review workflow runs through CLI and API.

## Pros and Cons of the Options

| Criterion | A. No SPA | B. Read-only dashboard |
|---|---|---|
| Complexity | Low | High (second toolchain, auth in the browser) |
| Azure cost | None | Static hosting, small |
| Security | No browser session surface | Session handling, CSRF, CSP |
| Maintainability | Python only | Python + frontend |
| Demo value | Good with curated HTML | Higher |

## More Information

- [Phase 0 analysis](../phases/phase-0-analysis.md), section 8 (D5)
