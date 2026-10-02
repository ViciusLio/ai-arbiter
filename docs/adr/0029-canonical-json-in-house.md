---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0029: Canonicalise audit entries with an in-house RFC 8785 serialiser that has no floats

## Context and Problem Statement

ADR-0017 hashes each audit entry over its canonical JSON form (RFC 8785, JCS). Whoever
receives an export must be able to recompute the chain with tools of their own choice, so
the bytes that are hashed must follow the standard exactly. The serialiser sits on the
integrity path of the product and in the base install.

## Considered Options

- **A.** Depend on a library that implements RFC 8785 (`rfc8785`, pure Python).
- **B.** Write a small canonicaliser limited to the types audit entries use: objects,
  arrays, strings, integers, booleans and null. No floating-point numbers.
- **C.** `json.dumps(sort_keys=True, separators=(",", ":"))`.

## Decision Outcome

Chosen option: **B**.

- `ai_arbiter.core.canonical_json.canonicalize` returns the UTF-8 bytes of the RFC 8785
  form.
- Floating-point numbers are refused with an error. The difficult part of RFC 8785 is the
  serialisation of floats; audit entries do not need them. Amounts of money are written
  as decimal strings, timestamps as RFC 3339 strings in UTC.
- Integers outside the range that JSON numbers represent exactly (magnitude above
  2^53 - 1) are refused, as the RFC requires.
- Object keys are sorted by UTF-16 code units, as the RFC requires; this differs from
  Python's default ordering for characters outside the Basic Multilingual Plane.
- Strings that are not valid Unicode (lone surrogates) are refused.
- The output for the supported types is exactly what any RFC 8785 implementation
  produces. The test suite checks the vectors of the RFC and compares the output with
  the `rfc8785` library, which is a development dependency only, on generated values.
- The same function produces the digest of the facts of a decision (`input_digest`).

### Consequences

- Good: no runtime dependency on the integrity path.
- Good: an export can be verified with any RFC 8785 library in any language.
- Bad: the code is ours to keep correct. It is about sixty lines and closed in scope.
- Bad: a future need for floats in audit entries would require either the full number
  algorithm or a string representation.

## Pros and Cons of the Options

| Criterion | A. Library | B. In-house without floats | C. `json.dumps` with sorted keys |
|---|---|---|---|
| Complexity | Lowest | Low: about sixty lines and the RFC vectors | Lowest |
| Azure cost | None | None | None |
| Scalability | Adequate | Adequate | Fastest |
| Security | One more dependency on the integrity path | No dependency; the risk is an error of ours | Output is not the standard form |
| Compliance / privacy | Verifiable with any RFC 8785 library | Verifiable the same way | A third party must reproduce Python's behaviour |
| Maintainability | Maintained upstream | Small, closed code | None |
| Lock-in | Low | None | On Python |

## More Information

- [ADR-0017](0017-audit-hash-chain-per-tenant.md)
- [RFC 8785: JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785)
