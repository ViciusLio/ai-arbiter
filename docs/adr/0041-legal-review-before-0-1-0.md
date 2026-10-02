---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0041: Release `0.1.0` only after a person with legal training has reviewed the AI Act rule pack

## Context and Problem Statement

The AI Act rule pack was written by an AI assistant from the Official Journal text. Its
questions summarise provisions that are longer and more qualified, in two languages.
Nobody with legal training has read it. `0.1.0` would be the first release without the
alpha label of a tool whose outputs name legal obligations.

## Considered Options

- **1.** `0.1.0` waits for a review of the rule pack by a person with legal training.
- **2.** `0.1.0` ships with a prominent notice that the pack was not reviewed.
- **3.** Decide later.

## Decision Outcome

Chosen option: **1**.

- Until the review, releases carry a pre-release version (`0.1.0aN`, `0.1.0bN`,
  `0.1.0rcN`) and every output keeps saying that results are indicative.
- The review covers: the facts and their wording in English and Italian, the rules and
  the provisions they cite, the application dates, the obligations listed for deployers,
  and the list of what the pack does not cover.
- Its outcome is recorded in the pack (`reviewed_by` as a role, not a name, and the
  date) and in the phase summary; corrections become a new pack version.
- The owner's comparison of the quoted articles with EUR-Lex (ADR-0034) is a separate,
  earlier step. It was not done on 2026-10-02 and the pack stays `review: pending`.
- Finding the reviewer is the owner's task. It is an open question until someone is
  named.

### Consequences

- Good: the first stable release rests on more than the assistant's reading of the text.
- Bad: the date of `0.1.0` depends on a person outside the project.
- Bad: a review is of one version of the pack; later changes need it again, in
  proportion to what changed.

## Pros and Cons of the Options

| Criterion | 1. Wait for the review | 2. Ship with a notice | 3. Decide later |
|---|---|---|---|
| Complexity | A dependency on a person | None | None |
| Azure cost | None | None | None |
| Scalability | Not affected | Not affected | Not affected |
| Security | Not affected | Not affected | Not affected |
| Compliance / privacy | Lowest risk of a user relying on a wrong rule | The risk is disclosed, not reduced | Unchanged |
| Maintainability | Reviews to repeat when the pack changes | None | None |
| Lock-in | None | None | None |

## More Information

- [ADR-0003](0003-deterministic-classifier-rules-as-data.md), [ADR-0034](0034-legal-text-from-the-publications-office.md)
- Improvement I-22 in the README
