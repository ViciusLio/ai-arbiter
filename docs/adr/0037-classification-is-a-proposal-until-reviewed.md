---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0037: Treat every classification as a proposal until a named person confirms or overrides it

## Context and Problem Statement

A deterministic classifier gives the same answer for the same facts (ADR-0003), but the
facts are declared by people and the outcome has legal weight. Arbiter is a support tool:
its outputs must not read as settled conclusions, and a reasoned disagreement with the
engine must be recordable.

## Considered Options

- **1.** Automatic and final; a person can only change the declared facts.
- **2.** Automatic, and a person may override the result with a reason.
- **3.** Every result is a proposal until a named person confirms it or overrides it with
  a reason.

## Decision Outcome

Chosen option: **3**.

- A classification is stored as computed and is never altered. Its status is `proposed`.
- A review is a separate record: reviewer, decision (`confirmed` or `overridden`), the
  tier chosen when overriding, reason, date. The effective tier is the reviewed one.
- Outputs show an unreviewed classification as indicative and say that it awaits review.
- When the facts or the rule pack change, a new classification supersedes the old one
  and needs its own review.
- Classifications and reviews are audit entries. The reviewer appears by identifier.
- Findings use the same pattern: a detection is a proposal, a person decides its status.

### Consequences

- Good: nothing is presented as settled until someone took responsibility for it.
- Good: the engine's result and the person's judgement are both kept.
- Bad: a review queue to work through; an unreviewed inventory stays "indicative".

## Pros and Cons of the Options

| Criterion | 1. Automatic and final: a person can only change the declared facts | 2. Automatic, and a person may override the result with a reason | 3. Every result is a proposal until a named person confirms it; that person may confirm or override with a reason |
|---|---|---|---|
| Complexity | Lowest | Low | Medium: a status and a review step |
| Azure cost | None | None | None |
| Scalability | Not affected | Not affected | A review queue to work through |
| Security | Not affected | The override is audited | Confirmation and override are audited |
| Compliance / privacy | Nobody is accountable for the result; no way to record a reasoned disagreement | The engine's result and the person's are both kept | Matches "support tool, not legal advice": nothing is presented as settled until a person took responsibility |
| Maintainability | Simple | Simple | A workflow to maintain, shared with findings |
| Lock-in | None | None | None |

## More Information

- [Phase 4 preparation](../phases/phase-4-preparation.md), decision P4-4
