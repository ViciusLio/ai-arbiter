---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0014: Detect PII with built-in pattern detectors by default, pluggable for more

## Context and Problem Statement

The brief requires PII redaction before persistence and PII checks in policy. Detection
runs on the request path, so it must be fast, and inside the offline CLI, so the default
cannot need a cloud service or a large model download. Italian text matters as much as
English.

## Considered Options

- **A.** Built-in detectors: patterns with checksum validation where one exists (email,
  phone, IBAN mod-97, payment card Luhn, Italian *codice fiscale* and *partita IVA*, IP
  addresses, common secret formats).
- **B.** Microsoft Presidio with spaCy models.
- **C.** Azure AI Language PII detection.

## Decision Outcome

Chosen option: **A as the default**, with **B and C as optional plugins** behind the
`PIIDetector` port (`ai-arbiter[pii]` for Presidio, `ai-arbiter[azure]` for C).

- **The default set covers EU and Italian formats** (added at acceptance): Italian
  *codice fiscale* and *partita IVA* with their check characters, IBAN for all SEPA
  countries (mod-97), EU VAT numbers, phone numbers in E.164 and in EU national formats,
  and identity documents (Italian identity card and passport numbers, EU passport
  formats), next to email, payment cards (Luhn), IP addresses and common secret formats.
- Identity document numbers have no public checksum. Those detectors need a context word
  near the match ("passaporto", "carta d'identità", "passport no.") and report a lower
  confidence than checksum-validated ones.
- Detector results report category, span and confidence; the detected text itself is
  never stored.
- **Limits are documented where users will see them** (added at acceptance): in the
  README, in the policy module documentation and in the output of the command that lists
  active detectors. Each detector states what it validates and what it misses.
- The documentation states plainly that the default does not detect names, addresses or
  free-text health data.
- Precision and recall of each detector are measured on the simulation scenarios and
  published.

### Consequences

- Good: deterministic, sub-millisecond, no extra dependency, works offline.
- Bad: low recall on unstructured PII in the default configuration. This is the most
  important limitation of the policy module and must not be hidden.
- Follow-up: redaction strategy (mask, hash, drop) is configurable per category.

## Pros and Cons of the Options

| Criterion | A. Built-in patterns | B. Presidio | C. Azure AI Language |
|---|---|---|---|
| Complexity | Low | Medium (models, language configuration) | Low to integrate |
| Azure cost | None | None (CPU and memory for models) | Per text record |
| Scalability | Excellent | CPU-bound; hundreds of MB per replica | Network call per request; quotas |
| Security | Text stays in process | Text stays in process | Text sent to another service |
| Compliance / privacy | No transfer; limited recall | No transfer; better recall | Additional processor; region must be pinned to the EU |
| Maintainability | Patterns maintained by hand | Maintained upstream | Maintained by Microsoft |
| Lock-in | None | None | Azure |
| Latency on the request path | Negligible | Tens of ms | Network round trip |

## More Information

- [Phase 0 analysis](../phases/phase-0-analysis.md), risk R5
