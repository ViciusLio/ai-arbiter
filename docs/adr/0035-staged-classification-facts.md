---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0035: Ask classification facts in stages and never read a missing answer as "no"

## Context and Problem Statement

The classifier decides from facts declared about a system (ADR-0003). The Regulation
makes fine distinctions, for example between the points of Annex III, so coarse facts
lose information; but a flat list of every distinction is long, and long forms are left
half empty. An empty answer must not turn into a classification.

## Considered Options

- **1.** One fact per legal provision, in a flat list of about sixty.
- **2.** About fifteen coarse facts.
- **3.** Stages: coarse areas first, then the detailed facts of the areas that apply.

## Decision Outcome

Chosen option: **3**.

- The stages follow the Regulation: scope and exclusions (Art. 2), prohibited practices
  (Art. 5), high-risk (Art. 6 with Annex I and Annex III), transparency (Art. 50), then
  controls the deployer attests.
- A fact declares its type, its stage, the provision it comes from and, for a detailed
  fact, the area fact it depends on. A detailed fact is asked only when its area applies.
- Rules are evaluated with three values: holds, does not hold, cannot be told. A
  comparison on an unanswered fact cannot be told; `all`, `any` and `not` combine the
  three values in the usual way, so an area answered "no" settles its detailed facts
  without asking them.
- The result lists the facts that are missing. When a rule that cannot be told could give
  a more severe outcome than the ones that hold, the tier is `undetermined`.

### Consequences

- Good: each rule cites the exact provision, and the form stays short for most systems.
- Good: an incomplete declaration yields `undetermined` and a list of questions, never a
  guess.
- Bad: the rule engine gains a second evaluation mode to keep correct.

## Pros and Cons of the Options

| Criterion | 1. One fact per legal provision (about 60, flat) | 2. A few coarse facts (about 15) | 3. Staged: coarse areas first, then the detailed facts of the areas that apply |
|---|---|---|---|
| Complexity | Medium: long but simple | Low | Medium |
| Azure cost | None | None | None |
| Scalability | New provisions add facts | Coarse facts hide distinctions the law makes | New areas add a stage |
| Security | Not affected | Not affected | Not affected |
| Compliance / privacy | Traceable to the article, tedious to fill: unanswered facts likely | Easy to fill, but a rule cannot cite the exact point of Annex III | Traceable to the article; unanswered facts are reported as missing, and the outcome is `undetermined` rather than a guess |
| Maintainability | One long list | Short, and wrong | Two short lists per area |
| Lock-in | None | None | None |

## More Information

- [Phase 4 preparation](../phases/phase-4-preparation.md), decision P4-2
