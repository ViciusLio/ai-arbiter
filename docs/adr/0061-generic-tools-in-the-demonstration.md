---
status: accepted
date: 2026-10-06
decision-makers: Project owner
---

# 0061: The demonstration uses generic tools, and says what was read about real ones

Refines [ADR-0060](0060-the-consulting-case-around-one-approved-model.md).

## Context and Problem Statement

The consulting demonstration named two real coding products as the tools of its
invented firm, with a notice that what a product offers is for each organisation to
check. Before the first release, with the pages public, the owner asked which approach
is best and left the choice to the implementer.

The documentation of the two products was read on 2026-10-06. One of them documents no
way to send its requests to another endpoint: its choice of models is governed inside
the product. The story showed that product being stopped by a gateway, which its
documentation does not support. A notice does not repair a scene that describes
something a product does not do.

## Considered Options

- **1.** Keep the product names, with the notices.
- **2.** Generic tools in the demonstration and on the public pages; the model names
  stay; a page says what was read about real products, with sources and a date.
- **3.** Keep one product, the one that documents another endpoint, and drop the other.

## Decision Outcome

Chosen option: **2**.

- The firm's tools are "Coding IDE" (`coding-ide`) and "Code assistant"
  (`code-assistant`). The approved family of models and the other engines keep their
  names: a model name is what a client asks for, and the rule is about it.
- `docs/scope-and-limits.md` records what the two vendors document and what follows for
  a gateway. No real product was connected (I-50).
- Option 3 would rest on one sentence of documentation and on nothing tried: tool
  calling through the gateway is untested.

### Consequences

- Good: the story claims nothing about a product that its vendor does not say.
- Good: the page on real tools makes the limit useful: "approved models only" is
  enforced at a gateway for some tools and inside the product for others.
- Bad: the story is less vivid without names people recognise.
- Bad: what vendors document changes; the page has a date and has to be read again
  before it is relied on.

## Pros and Cons of the Options

| Criterion | 1. Product names | 2. Generic tools | 3. One product |
|---|---|---|---|
| Complexity | None | Low: texts, data, tests | Low |
| Azure cost | None | None | None |
| Scalability | Not relevant | Not relevant | Not relevant |
| Security | No change | No change | No change |
| Compliance / privacy | A public page that describes a product inaccurately | Nothing claimed about a product | A claim that rests on documentation alone |
| Maintainability | Every vendor change can falsify the story | The story stays true | One vendor to follow |
| Lock-in | None | None | None |

## More Information

- `docs/scope-and-limits.md`, section "Real coding tools and a gateway"
