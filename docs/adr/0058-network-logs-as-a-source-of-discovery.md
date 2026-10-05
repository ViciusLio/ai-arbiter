---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0058: Network and SASE logs as a source of discovery, after 0.3

## Context and Problem Statement

Arbiter sees the AI use that passes through its gateway or is imported from another LLM
gateway. An organisation with a secure web gateway, a CASB or a SASE service has a log
of the rest. The owner wants that link on the wish list (I-48). The preparation,
[network-sase-preparation.md](../phases/network-sase-preparation.md), records what the
logs of four vendors hold, read on their documentation, and seven decisions.

## Considered Options

The options of each decision, N1 to N7, are in section 5 of the preparation, with their
comparison tables.

## Decision Outcome

Decided by the owner on 2026-10-05, each as recommended:

| # | Decision |
|---|---|
| N1 | In only: Arbiter reads network logs. Nothing is written into a network's policy |
| N2 | One generic "web access log" source, with ready mappings for the vendors as data |
| N3 | A line counts as AI use by the vendor's category when present, by a list shipped with Arbiter otherwise |
| N4 | The person is dropped at import; the department or group is kept |
| N5 | The logs arrive as a file given to `arbiter ingest` |
| N6 | Later, a file of approved and refused hosts for a person to load; no vendor API |
| N7 | The work is done after 0.3 (Azure) |

No code is written now. When the work starts, the mappings are checked against real
exports before anything is called verified, as I-31 asks for LiteLLM.

### Consequences

- Good: no credential of a network vendor is ever held by Arbiter, and no person's
  browsing is stored.
- Good: the inbound direction needs no new part of the architecture: a source behind
  `TelemetrySource`, and the discovery by group that exists.
- Bad: without the person, Arbiter says which department uses an undeclared AI service,
  not who; the organisation looks that up in its own log.
- Bad: a list of AI destinations shipped with Arbiter goes stale and must be maintained.
- Bad: a content field that some feeds carry, such as the prompt, must be dropped on
  the way in, and the importer has to say that it did.
- Open: whether importing network logs needs an agreement or a notice to employees is a
  question for the organisation's legal advice. Arbiter does not answer it.

## More Information

- [ADR-0019](0019-external-telemetry-ingestion.md),
  [ADR-0042](0042-discovered-systems-by-project.md)
