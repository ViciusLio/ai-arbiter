---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0036: Record the Article 6(3) derogation as claimed by the provider; do not compute it

## Context and Problem Statement

Article 6(3) lets a system listed in Annex III be treated as not high-risk under four
conditions, and never when it performs profiling of natural persons. Article 6(4) gives
the assessment to the provider, who documents it and registers the system (Article
49(2)). Arbiter covers the deployer first (ADR-0007).

## Considered Options

- **1.** The deployer records that the provider claims the derogation, with a reference
  to the provider's assessment.
- **2.** No derogation for deployers: an Annex III system is always high-risk.
- **3.** The tool evaluates the four conditions from declared facts.

## Decision Outcome

Chosen option: **1**.

- Two facts: the derogation is claimed, and a reference to the documented assessment.
- A system declared as profiling natural persons is high-risk whatever is claimed.
- A claimed derogation without a reference to the assessment raises a finding.
- When the organisation is itself the provider (ADR-0022), the same facts record its own
  assessment. The four conditions are not computed by Arbiter in either case.

### Consequences

- Good: the tool does not make a legal judgement the Regulation gives to the provider.
- Good: the evidence a deployer should hold is asked for.
- Bad: a wrong claim by a provider passes through; the finding checks that the evidence
  is referenced, not that it is sound.

## Pros and Cons of the Options

| Criterion | 1. A deployer records that the provider claims the derogation, with a reference to the provider's assessment | 2. No derogation for deployers: an Annex III system is always high-risk in the tool | 3. The tool evaluates the four conditions from facts the deployer declares |
|---|---|---|---|
| Complexity | Low | Lowest | Medium |
| Azure cost | None | None | None |
| Scalability | Not affected | Not affected | Not affected |
| Security | Not affected | Not affected | Not affected |
| Compliance / privacy | Follows Art. 6(4): the provider assesses, the deployer keeps evidence. Without the reference, a finding is raised | Over-classifies: safe, but reports obligations that may not apply | The tool would decide what the law gives the provider to assess |
| Maintainability | Simple | Simplest | Rules that mirror a legal judgement |
| Lock-in | None | None | None |

## More Information

- [Phase 4 preparation](../phases/phase-4-preparation.md), decision P4-3
