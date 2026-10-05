---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0052: A2A is handled through the official SDK, as an extra, behind a port

## Context and Problem Statement

A2A 1.0 defines eleven operations on three bindings, with a compatibility mode for 0.3 in the official Python SDK.

## Considered Options

- **1.** The official `a2a-sdk`, as an extra, behind a port, in `adapters`
- **2.** Arbiter's own models

## Decision Outcome

Chosen option: **1**.

`a2a-sdk` is an optional extra, imported only by an adapter; the rest of Arbiter sees a port. The base install stays free of protobuf and `google-api-core`.

### Consequences

- Good: a maintained implementation of the protocol and of card signing.
- Bad: a dependency on the SDK, contained by the port.

## Pros and Cons of the Options

| Criterion | 1. The official `a2a-sdk`, as an extra, behind a port, in `adapters` | 2. Arbiter's own models |
|---|---|---|
| Complexity | Medium | High: eleven operations and three bindings |
| Azure cost | None | None |
| Scalability | Not affected | Not affected |
| Security | A maintained implementation | Ours to get right |
| Compliance / privacy | Not affected | Not affected |
| Maintainability | Tracks 1.0 and the 0.3 compatibility mode | Ours to track |
| Lock-in | On the SDK, contained by the port | None |

## More Information

- [Phase 5 preparation](../phases/phase-5-preparation.md), decision P5-7: what was
  read on the official sources, and where
