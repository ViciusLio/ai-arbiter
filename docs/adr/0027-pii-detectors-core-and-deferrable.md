---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0027: Confirm the v0.1 split and divide the built-in PII detectors between core and v0.1.x

## Context and Problem Statement

ADR-0009 split v0.1 into a core and deferrable components. The owner named part of each
list; the rest was placed by the rule "does the demo still work without it?" and left as
open question Q1. Among the items placed in the core, PII detection is the heaviest:
ADR-0014 asks the default detector set to cover EU and Italian formats, and a large part
of that set (national phone formats of every member state, VAT numbers of every member
state, identity documents) has no checksum, so each pattern needs tuning against false
positives before it can be trusted on the request path.

## Considered Options

- **A.** Confirm the split of ADR-0009 as written, with every detector of ADR-0014 in
  the core.
- **B.** Confirm the split, but divide the detectors: those backed by a checksum or an
  unambiguous format in the core, the others in v0.1.x.
- **C.** Move PII detection out of the core.

## Decision Outcome

Chosen option: **B**. The placement of the items ADR-0009 did not name is confirmed:
policy and PII detection in the core; reports, local agent, discovery from traffic and
external anchoring among the deferrable components.

Built-in detectors in the core (`0.1.0`):

| Category | What is validated |
|---|---|
| `email` | Address syntax |
| `phone` | E.164 with a leading `+`; Italian national format (mobile and landline prefixes) |
| `iban` | Country code and length for the SEPA countries, mod-97 check |
| `payment_card` | 13 to 19 digits, Luhn check |
| `it_fiscal_code` | Italian *codice fiscale*: structure and check character, including the substitutions used for homonyms |
| `it_vat_number` | Italian *partita IVA*: 11 digits and check digit; requires a context word or the `IT` prefix |
| `ip_address` | IPv4 and IPv6 literals |
| `secret` | Common credential formats: private key blocks, JSON Web Tokens, well-known API key prefixes, Arbiter's own keys |

Deferred to v0.1.x:

- phone numbers in the national formats of the other member states;
- VAT numbers of the other member states;
- identity documents (Italian identity card and passport numbers, EU passport formats)
  with a context word;
- the measurement of precision and recall on the simulation scenarios, which are
  themselves deferrable (ADR-0009).

The duties of ADR-0014 that do not depend on the size of the set stay in the core: the
`PIIDetector` port, the redaction strategies per category, and the list of what each
detector validates and misses, shown by the CLI and in the README.

### Consequences

- Good: every detector in `0.1.0` rejects most false positives by construction, so
  redaction can be on by default.
- Good: the core of Phase 3 is smaller.
- Bad: until v0.1.x, a phone number written in a national format other than the Italian
  one, a foreign VAT number or a document number passes undetected. The limits list says
  so.
- Follow-up: this ADR refines ADR-0009 and ADR-0014; neither is superseded.

## Pros and Cons of the Options

| Criterion | A. Everything in the core | B. Split by validation strength | C. PII out of the core |
|---|---|---|---|
| Complexity | High: many patterns to tune | Medium | Low |
| Azure cost | None | None | None |
| Scalability | Same | Same | Same |
| Security | Widest coverage, more false positives | Narrower coverage, few false positives | Prompts reach providers unredacted |
| Compliance / privacy | Closest to ADR-0014 | Gaps are documented and dated | Conflicts with "PII is redacted before persistence" |
| Maintainability | Many hand-kept patterns from day one | Patterns added when they can be measured | Nothing to maintain |
| Lock-in | None | None | None |

## More Information

- [ADR-0009](0009-v0-1-scope.md), [ADR-0014](0014-pii-detection-built-in-and-pluggable.md)
- Open question Q1 in the [ADR index](README.md), closed by this decision
