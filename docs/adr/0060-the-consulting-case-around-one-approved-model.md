---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0060: The consulting demonstration is built around one approved model, and a run can be written as a page

Refines [ADR-0056](0056-a-demonstration-for-an-it-consulting-firm.md).

## Context and Problem Statement

The owner tried the consulting demonstration of ADR-0056 and asked for two things: a use
case closer to what a firm lives with, and something to show other than a terminal. The
case the owner described: one AI is approved, Claude, and every other is not; people use
tools such as Kiro and GitHub Copilot, which can run on several engines, and may use
them only with the approved one.

## Considered Options

The story:

- **1.** Keep the four generic systems of ADR-0056.
- **2.** Rebuild the case around one approved family of models and declared tools that
  could use other engines, named as the firm would name them.

What to show:

- **A.** The terminal output only.
- **B.** A page written by the run: one self-contained HTML file with the steps and the
  figures, as a deck.
- **C.** A web dashboard served by the application.

## Decision Outcome

Chosen: **2** and **B**, as the owner asked on 2026-10-05.

- The firm approves the Claude models and declares five systems: a chat assistant, Kiro,
  GitHub Copilot, the CV screening of HR and a mood analyser nobody bought. The run has
  thirteen steps; the central ones show the same tool allowed on the approved model and
  refused on another engine, by a rule that looks at the model and not at the tool.
- `arbiter demo tour --case consulting --report FILE` writes the run as a page. The page
  loads nothing from anywhere, holds no text of any request, and every figure on it
  comes from the run and from the tenant: among them a table of tool by model with the
  requests that went through and the ones that were refused.
- Product names are used as labels a firm gives its tools. The data, the page and the
  guide say that which engines a product offers, and whether it can be pointed at a
  gateway, is for each organisation to check with the vendor. No real product was
  connected: the requests of each tool are made by the demonstration with a key tied to
  the declared system.
- The model names are the ones a client would ask for; a stand-in answers them.

### Consequences

- Good: the case is the question firms ask first, which AI may we use and through what.
- Good: a page can be opened, sent and shown without a terminal and without a
  connection; it prints as a document.
- Bad: the case can be read as a statement about real products. The disclaimers are in
  the data, on the page and in the guide, and they have to stay there.
- Bad: the demonstration shows the rule working on requests that pass through Arbiter.
  A tool that talks to its vendor directly is outside it; that gap is ADR-0058.
- Bad: the page is a second template to keep in step with the presentation's style.
- Bad: its author has not seen the page in a browser; its script was checked for syntax
  and its content by tests.

## Pros and Cons of the Options

| Criterion | A. Terminal only | B. A page written by the run | C. A dashboard |
|---|---|---|---|
| Complexity | None | Low: a template and a renderer | High: a new part of the product |
| Azure cost | None | None | None |
| Scalability | Not relevant | Not relevant | Not relevant |
| Security | No new surface | A static file; every value is escaped; nothing is fetched | A new surface to secure |
| Compliance / privacy | No content shown | No request text on the page | To be designed |
| Maintainability | Nothing | A template with its texts in two languages | Much more |
| Lock-in | None | None | A front-end stack |

## More Information

- `docs/demo.md`, `src/ai_arbiter/templates/demo-report.html.j2`,
  `examples/consulting/live.env`
