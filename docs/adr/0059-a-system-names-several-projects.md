---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0059: A system names several projects, and a key belongs to a system through its project

Refines [ADR-0042](0042-discovered-systems-by-project.md).

## Context and Problem Statement

A declared system could name one project of the gateway, and that had one effect: the
project's unattributed requests counted as the system's own in scans. Two things were
missing (I-33). An organisation that works by engagement runs one system in several
projects. And the gateway applied the tier of a system only to keys tied to it one by
one, so a key issued in the project without that tie escaped the policy on prohibited
practices and the routing constraints.

Two questions: how a declaration names several projects (S1), and whether the gateway
takes the system of a key from its project (S2). The owner left both to the implementer
on 2026-10-05, asking for the best way.

## Considered Options

S1, several projects:

- **S1-1.** A list, `project_ids`, stored in a link table.
- **S1-2.** One project per declaration, as before; one declaration per project.

S2, the system of a key that names none:

- **S2-1.** Never from the project, as before.
- **S2-2.** From the project, when exactly one declared system names it.
- **S2-3.** Always from the project; of several systems, the most severe tier.

## Decision Outcome

Chosen: **S1-1** and **S2-2**.

- A declaration lists `project_ids`. The earlier `project_id` is still read and means a
  list of one. The table `ai_system_project` replaces the column; migration 0011 moves
  what was there.
- At the gateway and at both proxies, a key tied to no system belongs to the system
  that names the key's project, when exactly one does. From that point the request is
  that system's: its tier decides, its budgets and grants apply, and the interaction or
  the invocation is recorded under it.
- When two or more systems name the project, the key belongs to none of them, as before
  this decision. To choose would be to guess, and S2-3 would let one declaration stop
  every key of a project that other systems share.
- A key tied to a system keeps that system, whatever its project.

### Consequences

- Good: declaring a project is enough for the gateway to apply the tier to its keys;
  nobody has to remember to tie each new key.
- Good: one system can cover the projects of several engagements.
- Bad: a declaration now changes what the gateway does to keys that were not touched: a
  project named by a system classified as a prohibited practice gets no model at the
  next request. That is the purpose, and it is also a way to stop a project by mistake.
  The change of a declaration is audited.
- Bad: a project shared by several systems is still one candidate in discovery and its
  keys still have to be tied one by one.
- Bad: one more query per request for keys tied to no system.

## Pros and Cons of the Options

| Criterion | S2-1. Never | S2-2. When exactly one | S2-3. Always, most severe |
|---|---|---|---|
| Complexity | None | Low | Medium: a rule to order tiers across systems |
| Azure cost | None | None | None |
| Scalability | No query | One indexed query for keys without a system | The same, plus classifications of several systems |
| Security | A key without the tie escapes the tier | The tier follows the project; no guess | The strictest reading; one declaration can stop a shared project |
| Compliance / privacy | The declared and the enforced can differ | They agree where the declaration is unambiguous | They agree, by over-blocking |
| Maintainability | Keys tied by hand | One rule, easy to state | Surprising denials to explain |
| Lock-in | None | None | None |

## More Information

- [ADR-0037](0037-classification-is-a-proposal-until-reviewed.md): the tier applied is the
  effective one, reviewed or not, as for a key tied to the system
