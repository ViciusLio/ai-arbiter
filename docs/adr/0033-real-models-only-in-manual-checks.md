---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0033: Check provider adapters against real models by hand; no automated test depends on one

## Context and Problem Statement

The adapters for OpenAI-compatible endpoints and Azure OpenAI were built in Phase 3 and
tested only against a simulated HTTP transport. A simulation proves that the code does
what its author thinks the wire format is; it cannot prove that a real server agrees.
Running a real model costs something: credentials and money for a hosted one, download
size and compute time for a local one, in a Codespace with a free quota.

## Considered Options

- **A.** Run a local OpenAI-compatible server (Ollama) in the Codespace, by hand, with
  the smallest model that can answer a chat request, and remove it afterwards.
- **B.** Use a hosted endpoint with a key supplied by the owner.
- **C.** Leave the verification to just before `0.1.0`.

## Decision Outcome

Chosen option: **A** for the OpenAI-compatible adapter, with rules that hold from now on:

- **No automated test and no CI job depends on a real model.** The test suite and CI use
  the mock provider and simulated transports only.
- A test that calls a real endpoint may exist only if it is opt-in: skipped unless an
  environment variable names the endpoint, and never set in CI.
- A local model server runs as a container, not installed on the machine, and is stopped
  and removed with its image and its model when the check is done. The space freed is
  reported.
- Prompts sent to any real model are synthetic. No real personal data, no content of the
  owner or of third parties.
- What a manual check covered, and what it did not, is written in the phase summary.
- The Azure OpenAI adapter is checked in Phase 6, when Azure resources exist (ADR-0008).

### Consequences

- Good: the suite stays fast, free and deterministic, and passes with no network.
- Good: the adapter is confronted with a real implementation of the wire format.
- Bad: a manual check is a snapshot. A later change to the adapter, or to the server, is
  not caught until someone repeats it.
- Bad: one local server is one implementation; other OpenAI-compatible services may
  differ in details.

## Pros and Cons of the Options

| Criterion | A. Local server, by hand | B. Hosted endpoint with a key | C. Later |
|---|---|---|---|
| Complexity | Low | Low | None |
| Azure cost | None | None, or the price of the calls | None |
| Scalability | Limited by the Codespace: small models only | Any model | Not applicable |
| Security | Nothing leaves the Codespace | A credential to handle; prompts leave | Nothing |
| Compliance / privacy | Synthetic prompts, local | Synthetic prompts, sent to a third party | Nothing |
| Maintainability | Repeatable from the opt-in test | Repeatable while the key lasts | The gap stays open |
| Lock-in | None | On the chosen service | None |

## More Information

- [ADR-0013](0013-own-llm-provider-adapters.md), [ADR-0008](0008-local-only-until-phase-6.md)
- [Phase 3 summary](../phases/phase-3-gateway.md), "Not verified"
