---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0001 — Record decisions as MADR files, never delete them

## Context and Problem Statement

Arbiter is also a portfolio project: the reasoning behind each choice is part of the
deliverable. The project brief requires every non-trivial choice to be evaluated before it
is implemented and to stay traceable afterwards.

## Considered Options

- **A.** MADR files in `docs/adr/`, one per decision, immutable once accepted.
- **B.** A single running `DECISIONS.md`.
- **C.** Decisions only in commit messages and pull requests.

## Decision Outcome

Chosen option: **A**, as mandated by the brief.

Process for every non-trivial choice:

1. Present at least two options in a table covering complexity, Azure cost, scalability,
   security, compliance/privacy impact, maintainability and lock-in, with a recommendation.
2. Wait for the project owner's decision.
3. Record it as `docs/adr/NNNN-title.md` with status `proposed`, `accepted` or
   `superseded by ADR-NNNN`.
4. Link the ADR from `CHANGELOG.md` and from the index in `docs/adr/README.md`.

An ADR may be written with status `proposed` to carry the option table; it can be edited
freely until accepted. After acceptance it is changed only by a new ADR that supersedes it.

### Consequences

- Good: decisions are reviewable one at a time and survive refactors.
- Bad: more files to keep indexed; the index is updated at the end of every phase.

## More Information

- [Project brief](../PROJECT_BRIEF.md), section "Decisioni e tracciabilità"
- [MADR](https://adr.github.io/madr/)
