---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0018: Persist interaction metadata only; make redacted content an opt-in per system

## Context and Problem Statement

The gateway sees prompts and completions, which may contain personal data and trade
secrets. The brief requires data minimisation, redaction before persistence, configurable
retention and EU residency. Some uses do need content: certain scanner rules, incident
analysis, and record-keeping for systems that will be high-risk.

## Considered Options

- **A.** Store metadata only. Never persist prompt or completion text.
- **B.** A plus an opt-in, per AI system, to store redacted content with a retention
  period.
- **C.** Store full content, encrypted.

## Decision Outcome

Chosen option: **B**, with the opt-in off by default.

- Always stored per interaction: identifiers, timing, models, token counts, cost, policy
  outcome, PII **categories** detected (not values), and a keyed fingerprint of the
  prompt.
- The fingerprint is an HMAC with a per-tenant key over the normalised prompt. It allows
  duplicate detection for caching recommendations without storing or exposing the text;
  a plain hash would allow guessing short prompts.
- With the opt-in, content passes through redaction first and is stored in a separate
  table with an expiry date. A purge job deletes expired rows.
- Retention is configured per tenant and per risk class, with a floor where the law sets
  one. To verify in Phase 4 against the primary source: deployers of high-risk systems
  must keep automatically generated logs for at least six months (Article 26(6)).
- Audit entries are never purged by retention; they hold no content (ADR-0017).

### Consequences

- Good: the default installation stores nothing that a breach could expose as content.
- Bad: with the default, scanner rules that need content cannot run and say so.
- Bad: the redacted store is only as good as PII detection (ADR-0014).

## Pros and Cons of the Options

| Criterion | A. Metadata only | B. Metadata + opt-in redacted content | C. Full content, encrypted |
|---|---|---|---|
| Complexity | Low | Medium (retention, purge) | Medium (key management) |
| Azure cost | Lowest storage | Grows with opted-in systems | Highest |
| Scalability | Small rows | Larger rows in a separate table | Largest |
| Security | Nothing sensitive to steal | Limited to opted-in systems, redacted | High-value target |
| Compliance / privacy | Strongest minimisation; cannot meet content-based needs | Minimisation by default, justified exceptions | Hard to justify as a default |
| Maintainability | Simple | Purge job and policy to maintain | Key rotation |
| Lock-in | None | None | None |

## More Information

- [Data model](../architecture/data-model.md), `interaction` and `payload_blob`
