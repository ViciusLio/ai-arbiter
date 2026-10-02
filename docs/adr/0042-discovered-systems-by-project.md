---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0042: A system discovered from traffic is identified by its project

## Context and Problem Statement

Traffic that is attributed to no declared system is today one finding for the whole
tenant (`SCAN-UNATTRIBUTED-TRAFFIC`). Discovery turns it into candidates: things that
look like AI systems nobody declared. A candidate needs an identity that stays the same
from one scan to the next, or the same undeclared use is reported again and again under
new names.

A stored interaction holds the project and the team of the API key that made it, the
model, the provider and, for imported records, the source and the system the source
named.

## Considered Options

- **1.** One candidate per API key (imported records: key alias).
- **2.** One candidate per project (imported records: team alias), with the models it
  used as evidence.
- **3.** One candidate per pair of project and model.
- **4.** A grouping configurable per source, project by default.

## Decision Outcome

Chosen option: **2**.

- Native traffic is grouped by `project_id`. Imported traffic is grouped by source and
  by the label the importer keeps for the team; records with neither stay under the
  tenant-wide finding.
- A candidate is a proposal, like every other outcome (ADR-0037): a finding, and
  `arbiter systems discover`, which prints a draft declaration for a person to
  complete. Nothing is declared automatically, and a draft carries no fact: an
  unanswered question is never read as "no" (ADR-0035).
- The models, the number of requests and the categories of personal data detected are
  evidence of the candidate, not part of its identity.

### Consequences

- Good: keys rotate and models change; a project does not, so a candidate is stable.
- Good: a project is something a person can go and ask about.
- Bad: a project that runs several systems appears as one candidate. The person who
  completes the draft splits it.
- Bad: imported records without a team label cannot be grouped.

## Pros and Cons of the Options

| Criterion | 1. API key | 2. Project | 3. Project and model | 4. Configurable |
|---|---|---|---|---|
| Complexity | Low | Low | Medium | Medium |
| Azure cost | None | None | None | None |
| Scalability | Many candidates | Few, stable | A new candidate at every model change | As 2 |
| Security | Identifiers only | Identifiers only | Identifiers only | Identifiers only |
| Compliance / privacy | A key can belong to one person | A project is not a person | As 2 | Depends on the label chosen |
| Maintainability | Rotation duplicates candidates | Good | Deduplication rules | More configuration to explain |
| Lock-in | None | None | None | None |

## More Information

- [ADR-0009](0009-v0-1-scope.md), [ADR-0019](0019-external-telemetry-ingestion.md),
  [ADR-0037](0037-classification-is-a-proposal-until-reviewed.md),
  [ADR-0040](0040-deferrable-items-before-0-1-0.md)
