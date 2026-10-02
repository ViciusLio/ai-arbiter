---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0013 — Write thin provider adapters instead of depending on a provider library

## Context and Problem Statement

`llm_router` must call model providers behind the `LLMProvider` port. v0.1 needs Azure
OpenAI, any OpenAI-compatible endpoint, and a mock. Both real targets speak the OpenAI
wire format and differ in URL shape and authentication.

## Considered Options

- **A.** Own adapters over an async HTTP client: one OpenAI-wire-format adapter with two
  flavours (generic, Azure) plus a mock.
- **B.** LiteLLM SDK as the provider layer.
- **C.** Official `openai` Python SDK for both flavours.

## Decision Outcome

Chosen option: **A**.

- Azure OpenAI is among the providers supported from v0.1 (confirmed at acceptance).
- The generic adapter covers OpenAI, Ollama, vLLM and most hosted services.
- The Azure flavour adds deployment mapping, API version and authentication (API key
  from the secret store, or Entra ID token from an adapter in `adapters.azure`).
- The mock adapter is deterministic and scriptable (latency, errors, token counts); it
  backs the test suite and the simulation scenarios.
- A LiteLLM-backed adapter can be added later as a plugin for breadth.

### Consequences

- Good: the data path depends on one HTTP client; streaming, timeouts and retries are
  fully under control and testable.
- Bad: each additional non-OpenAI wire format is new work. This matches ADR-0002: provider
  breadth is not a goal.
- Bad: provider quirks (error shapes, usage in streaming) must be handled by hand.

## Pros and Cons of the Options

| Criterion | A. Own adapters | B. LiteLLM SDK | C. `openai` SDK |
|---|---|---|---|
| Complexity | Medium | Low | Low |
| Azure cost | None | None | None |
| Scalability | Full control of connection pooling and streaming | Good; internals not under control | Good |
| Security | Minimal dependency surface in the path that carries credentials | Large dependency tree in that path | Small |
| Compliance / privacy | Exactly known what is sent and logged | Library has its own logging and callbacks to disable | Known |
| Maintainability | Quirks handled by hand | Provider updates for free | Two flavours supported upstream |
| Lock-in | None | On LiteLLM's abstractions | On the SDK's types |
| Provider breadth | Narrow | Very wide | OpenAI-compatible only |

## More Information

- [ADR-0002](0002-compliance-first-positioning.md)
