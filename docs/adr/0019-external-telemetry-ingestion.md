---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0019 — Ingest external gateway data through source adapters into one canonical record

## Context and Problem Statement

ADR-0002 requires the compliance toolkit to work with data from gateways other than
Arbiter's own, naming LiteLLM and Azure API Management. Each source describes an LLM call
differently, and the downstream modules (inventory discovery, scanner, FinOps) must not
care where a record came from.

## Considered Options

- **A.** A canonical `InteractionRecord` owned by Arbiter, and one `TelemetrySource`
  adapter per external system that maps into it. Arbiter's own gateway is just another
  source.
- **B.** Adopt the OpenTelemetry GenAI semantic conventions as the canonical format and
  accept only OTLP.
- **C.** Per-source pipelines with no shared record.

## Decision Outcome

Chosen option: **A**, with field semantics kept close to the OpenTelemetry GenAI
conventions so that an OTLP source adapter is a straightforward mapping.

The OpenTelemetry GenAI conventions are not adopted as the internal contract: they are
still in Development status, were moved to a dedicated repository in June 2026, and
attribute names may change. Arbiter's record must stay stable across those changes.

Sources and schedule, as set by the project owner at acceptance:

| Source | Mechanism | Target |
|---|---|---|
| Native gateway | In-process event | v0.1 |
| Generic JSONL file | `arbiter ingest <file>` in canonical format | v0.1 |
| LiteLLM | File import of its standard logging payload | v0.1 |
| LiteLLM | HTTP push endpoint | v0.2 |
| Azure API Management | Pull from Log Analytics (`ApiManagementGatewayLlmLog`) | v0.2 |
| OTLP (GenAI spans) | Receiver endpoint | After the conventions stabilise |

The Azure API Management adapter was proposed for v0.3 and moved to v0.2 by the project
owner. Because no Azure resource exists before Phase 6 (ADR-0008), in v0.2 it is built
and tested against recorded log samples; validation against a live API Management
instance happens in Phase 6.

Rules for every source:

- The adapter performs minimisation: content fields are dropped or redacted before the
  record enters Arbiter (ADR-0018).
- Each record keeps `source` and `source_record_id`; ingestion is idempotent on that pair.
- Missing fields stay missing. A record without token counts is still useful for
  inventory discovery; FinOps skips it and reports the gap.
- Mapping to an AI system uses, in order: an explicit tag in the source metadata, a
  configured mapping (key, team, API id → system), otherwise "unattributed", which is
  itself surfaced as a finding.

### Consequences

- Good: compliance modules are tested once, against the canonical record.
- Good: the toolkit is useful to teams that will never deploy Arbiter's gateway.
- Bad: each adapter tracks a third party's log format and can break when it changes;
  adapters carry contract tests with recorded samples and declare the source versions
  they were tested against.
- Bad: externally ingested records have no Arbiter policy decision and no audit chain
  entry for the original call; the audit log records the ingestion itself.

## Pros and Cons of the Options

| Criterion | A. Canonical record + adapters | B. OTLP GenAI only | C. Per-source pipelines |
|---|---|---|---|
| Complexity | Medium | Low in Arbiter, high for users who must emit OTLP | High |
| Azure cost | Log Analytics queries for APIM | Same | Same |
| Scalability | Batch and streaming adapters | OTLP is built for volume | Varies |
| Security | Adapter is the single minimisation point | Content may arrive in span attributes | Minimisation repeated per pipeline |
| Compliance / privacy | Provenance kept per record | Depends on the emitter | Inconsistent |
| Maintainability | One mapping per source | Tied to an unstable convention | Duplicated logic |
| Lock-in | None | On a moving specification | None |

## More Information

- [ADR-0002](0002-compliance-first-positioning.md)
- [LiteLLM StandardLoggingPayload](https://docs.litellm.ai/docs/proxy/logging_spec)
- [Azure API Management — llm-emit-token-metric policy](https://learn.microsoft.com/en-us/azure/api-management/llm-emit-token-metric-policy)
- [State of the OpenTelemetry GenAI conventions, July 2026](https://john-hodge.com/blog/opentelemetry-genai-semantic-conventions/)
