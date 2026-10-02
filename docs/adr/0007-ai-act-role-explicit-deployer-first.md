---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0007: Model the AI Act role explicitly; cover the deployer first

## Context and Problem Statement

Obligations under the AI Act depend on the operator's role (provider, deployer, importer,
distributor, authorised representative, product manufacturer), not only on the risk class
of the system. The brief did not mention roles. Whoever puts a gateway in front of
third-party models is almost always a deployer.

## Considered Options

- **A.** Deployer-first rules, with the role as an explicit field of the data model.
- **B.** Cover provider and deployer obligations from the start.
- **C.** Leave the role implicit (assume deployer everywhere).

## Decision Outcome

Chosen option: **A**. The project owner requires the role to be **an explicit field of
the data model**, so that provider, importer and distributor can be added without a
schema change.

- The role is a closed enumeration covering all operator roles defined in Article 3.
- v0.1 rule packs contain obligations for the deployer role only. Rules declare which
  roles they apply to, so a system with another role is reported as "not yet covered"
  rather than silently treated as a deployer.

### Consequences

- Good: no obligation is attributed to the wrong role.
- Bad: provider-side obligations (including GPAI model providers) are absent in v0.1 and
  the output must say so.
- Open point for Phase 1: an operator can hold more than one role for the same system
  (for example, building a system and using it in-house). The data model proposal stores
  roles as a one-to-many relation rather than a single column; see
  [data model](../architecture/data-model.md).

## Pros and Cons of the Options

| Criterion | A. Deployer-first, explicit role | B. Provider + deployer now | C. Implicit role |
|---|---|---|---|
| Complexity | Medium | High (Annex IV, conformity assessment) | Low |
| Compliance accuracy | Correct for the covered role, explicit about the rest | Broadest | Wrong for non-deployers |
| Maintainability | Rule packs grow per role | Large rule set from day one | Schema change later |

## More Information

- [Phase 0 analysis](../phases/phase-0-analysis.md), sections 3 (A2, A4) and 8 (D6)
