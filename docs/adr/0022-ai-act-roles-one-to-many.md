---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0022: Store AI Act roles as a one-to-many relation of the AI system

## Context and Problem Statement

[ADR-0007](0007-ai-act-role-explicit-deployer-first.md) requires the AI Act operator role
to be an explicit field of the data model. One organisation can hold more than one role
for the same system: building a system and using it in-house makes it both provider and
deployer, and a deployer that substantially modifies a system takes on provider
obligations. A single column cannot express that.

## Considered Options

- **A.** A child table, `ai_system_role`, with one row per role held, each with the basis
  for the role and the date it applies from.
- **B.** A single `role` column on `ai_system`.
- **C.** A JSON list of roles on `ai_system`.

## Decision Outcome

Chosen option: **A**. This refines ADR-0007 and does not supersede it: the role stays
explicit and enumerated, and the deployer is still the first role covered by rules.

- `role` is the closed enumeration of ADR-0007.
- A system must have at least one role before it can be classified.
- The classifier evaluates obligations per role and reports roles not yet covered by the
  rule pack as such.

### Consequences

- Good: obligations are attributed per role, which is how the regulation assigns them.
- Good: `basis` and `since` record why and from when a role applies, which is what a
  reviewer asks first.
- Bad: one more table and a join; "the role of a system" becomes "the roles of a system"
  in every API and report.

## Pros and Cons of the Options

| Criterion | A. Child table | B. Single column | C. JSON list |
|---|---|---|---|
| Complexity | Low to medium | Lowest | Low |
| Azure cost | None | None | None |
| Scalability | Indexed, queryable | Indexed | Not portably queryable (ADR-0015) |
| Security | - | - | - |
| Compliance / privacy | Correct for multi-role operators; basis recorded | Wrong for multi-role operators | Correct, without basis or dates |
| Maintainability | Standard relation | Schema change when the second role appears | Validation in application code only |
| Lock-in | None | None | None |

## More Information

- [Data model](../architecture/data-model.md), section "AI Act role"
