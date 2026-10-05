---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0056: A demonstration built on an IT consulting firm, with its internal regulation as a policy pack

## Context and Problem Statement

The guided demonstration (`arbiter demo tour`) shows the product in general. The owner
wants a demonstration that follows one use case from end to end: an IT consulting firm
that uses several AI tools, is subject to the AI Act, and monitors and intervenes with
internal regulations. Three things had to be decided: what form the demonstration
takes, how an internal regulation is expressed, and what answers in place of a model.

## Considered Options

Form of the demonstration:

- **F1.** The case inside the guided demonstration, in one command.
- **F2.** F1, plus a script for a live session: the service running, real commands one
  at a time, reports and digest opened in a browser.
- **F3.** F2, plus a web dashboard.

The internal regulation:

- **R1.** A policy pack file made of the default rules plus the firm's own, with the
  mechanisms that exist: the model allowlist, redaction, budgets, grants.
- **R2.** A pack of its own that the scan reads too, with findings apart from the ones
  of the AI Act.

The model:

- **M1.** The mock provider.
- **M2.** M1, plus a real local model in a container as a documented variant.

## Decision Outcome

Chosen: **F2, R1, M1**, as recommended and confirmed by the owner on 2026-10-05.

- `arbiter demo tour --case consulting` follows an invented firm in eleven steps, in a
  tenant of its own, `demo-consulting`. Its systems and its regulation are data, in
  `src/ai_arbiter/scenarios/consulting/`.
- The regulation is `policy.yaml` there: the default policy and two rules of the firm,
  `IR-HIGH-RISK-NOT-REVIEWED` and `IR-CREDENTIAL-IN-PROMPT`, over facts the gateway
  already computes. No code was added to the policy engine.
- `docs/demo.md` is the script of the live session.

### Consequences

- Good: the case shows that an organisation's own rules need no code, only a file.
- Good: the case is a test, and fails when a rule or the gateway changes an outcome.
- Bad: the internal rules show as refused requests and audit entries, not as findings
  of the scan. R2 stays open for when that is asked.
- Bad: the case was written by the author of the rules, like the scenarios (I-35).
- Bad: without a dashboard, a live session is a terminal and two HTML pages.

## Pros and Cons of the Options

| Criterion | F1 | F2 | F3 |
|---|---|---|---|
| Complexity | Low | Medium: a script to keep true | High: a new part of the product |
| Azure cost | None | None | None |
| Scalability | Not relevant | Not relevant | Not relevant |
| Security | Invented data, one process | Invented data, a local service | A new surface to secure |
| Compliance / privacy | No real data | No real data | No real data |
| Maintainability | Covered by a test | The script is checked by hand | Much more to maintain |
| Lock-in | None | None | A front-end stack |

| Criterion | R1 | R2 |
|---|---|---|
| Complexity | Low: a file | Medium: scanner, reports, digest |
| Security | Enforced before a request leaves | The same, plus reporting |
| Compliance / privacy | Internal rules are kept apart from the AI Act by their ids | Kept apart by pack |
| Maintainability | One more example to keep in step with the default pack | A new kind of pack |

## More Information

- [ADR-0012](0012-unified-declarative-rule-engine.md), [ADR-0033](0033-real-models-only-in-manual-checks.md),
  [ADR-0043](0043-simulation-scenarios-as-data.md)
- `docs/demo.md`
