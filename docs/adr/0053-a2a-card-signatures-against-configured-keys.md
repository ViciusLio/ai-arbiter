---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0053: A card signature is verified only against keys the operator configured

## Context and Problem Statement

A card may be signed, and its signature may name the URL of the key set to verify it with (`jku`). A card that brings its own key vouches for itself.

## Considered Options

- **1.** Keys the operator configured, by key id; `jku` is ignored
- **2.** As 1, and `jku` is followed over HTTPS for domains on an allowlist
- **3.** `jku` is followed wherever it points

## Decision Outcome

Chosen option: **1**.

Signatures are verified against keys configured by the operator, found by key id, with an explicit list of accepted algorithms. `jku` is ignored: the server never fetches a URL a card names. An unsigned card, or one signed with an unknown key, is registered as unverified and reported as a finding; whether such an agent may be called is a policy rule. Checked on 2026-10-05: `a2a-sdk[signing]` 1.2.1 provides a verifier that takes a key provider and a list of algorithms, which is what this needs.

### Consequences

- Good: a verified card means that someone the operator trusts signed it.
- Good: no request leaves the server because a card asked for it.
- Bad: keys are rotated by hand. Following `jku` for listed domains can be added later.

## Pros and Cons of the Options

| Criterion | 1. Keys the operator configured, by key id; `jku` is ignored | 2. As 1, and `jku` is followed over HTTPS for domains on an allowlist | 3. `jku` is followed wherever it points |
|---|---|---|---|
| Complexity | Low | Medium | Low |
| Azure cost | None | None | None |
| Scalability | No request is made | One request per key set, cached | The same |
| Security | Only trusted keys | Trust by domain; requests leave the server to listed hosts only | A card vouches for itself, and the server fetches any URL a card names |
| Compliance / privacy | A verified card means something | The same | It means nothing |
| Maintainability | Keys are rotated by hand | Rotation follows the key set | The same |
| Lock-in | None | None | None |

## More Information

- [Phase 5 preparation](../phases/phase-5-preparation.md), decision P5-8: what was
  read on the official sources, and where
