---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0038: Set retention defaults, a six-month floor for high-risk systems, and a purge command

## Context and Problem Statement

The brief asks for data minimisation and configurable retention. Phase 1 proposed
defaults and left legal minimums to be verified. Verified in the consolidated text:
deployers of high-risk systems keep automatically generated logs "for a period
appropriate to the intended purpose [...] of at least six months, unless provided
otherwise in applicable Union or national law" (Article 26(6); Article 19(1) says the
same for providers).

## Considered Options

- **1.** The defaults of the data model, no floor by risk class, no purge yet.
- **2.** The same defaults, a six-month floor for interactions of systems classified
  high-risk, and a purge command.
- **3.** Keep everything; retention documented, not enforced.

## Decision Outcome

Chosen option: **2**.

| Data | Default | Configurable |
|---|---|---|
| Interactions | 13 months | Per deployment and per tenant; never less than six months for a system whose effective tier is high-risk |
| Outbox events | 7 days after dispatch | Per deployment |
| Audit entries, usage roll-ups | Kept | No |
| Classifications, findings and their reviews | Kept while the system exists | No, in v0.1 |

- `arbiter retention purge` deletes what is past its period, in one transaction per
  tenant, and writes one audit entry with counts and cut-off dates. `--dry-run` reports
  without deleting. Scheduling is external (cron, a container job).
- Roll-ups are not purged: usage totals survive the interactions they were built from.

### Consequences

- Good: storage is bounded and minimisation is delivered, not only promised.
- Good: the floor rests on a provision that was read in the primary text.
- Bad: the floor follows the classification; a system wrongly left unclassified has no
  floor. The default of 13 months is above it in any case.
- Bad: national law may require longer periods; that is for the operator to configure.

## Pros and Cons of the Options

| Criterion | 1. The defaults of the data model, no floor by risk class, no purge yet | 2. The same defaults, a six-month floor for interactions of systems classified high-risk, and a purge command | 3. Keep everything; retention is documented and not enforced in v0.1 |
|---|---|---|---|
| Complexity | Low | Medium: a purge job and its tests | Lowest |
| Azure cost | Storage grows | Bounded storage | Storage grows without bound |
| Scalability | Tables grow | Tables bounded by the retention period | Tables grow |
| Security | More data kept than needed | Less data to lose | Most data to lose |
| Compliance / privacy | Minimisation promised and not delivered | Minimisation delivered; the floor is tied to a verified provision; the purge is audited | Hard to defend under the GDPR storage limitation principle |
| Maintainability | Nothing to run | One command, scheduled outside Arbiter | Nothing to run |
| Lock-in | None | None | None |

## More Information

- [Phase 4 preparation](../phases/phase-4-preparation.md), decision P4-5
