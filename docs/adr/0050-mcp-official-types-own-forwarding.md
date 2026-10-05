---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0050: MCP messages come from the official types package; the forwarding is Arbiter's own

## Context and Problem Statement

The official Python SDK, `mcp`, is built for clients and servers and brings a second HTTP stack. Its messages are published separately as `mcp-types`.

## Considered Options

- **1.** The official `mcp` SDK, as an extra
- **2.** The official `mcp-types` package for the messages, and Arbiter's own forwarding over the HTTP client it already has
- **3.** Arbiter's own models and forwarding

## Decision Outcome

Chosen option: **2**.

The proxy uses `mcp-types` for the messages, the protocol constants and the JSON-RPC envelope, and forwards with the HTTP client the gateway already has. The package is an optional extra. The check the preparation asked for was made on 2026-10-05 on `mcp-types` 2.2.0: it depends only on Pydantic and `typing-extensions`, and holds both eras of the protocol, the version constants and the error codes. The mock MCP server of the tests and of the demo may use the full SDK.

### Consequences

- Good: no second HTTP stack in the data path; the types follow the specification.
- Bad: the forwarding, the header validation and the error mapping are ours to keep in step with the revision.

## Pros and Cons of the Options

| Criterion | 1. The official `mcp` SDK, as an extra | 2. The official `mcp-types` package for the messages, and Arbiter's own forwarding over the HTTP client it already has | 3. Arbiter's own models and forwarding |
|---|---|---|---|
| Complexity | Medium: an SDK built for clients and servers, used as a proxy | Low to medium | Medium |
| Azure cost | None | None | None |
| Scalability | Unknown until measured | The proxy forwards bytes | The same |
| Security | A second HTTP stack (`httpx2`, Starlette, uvicorn) in the data path | No new stack | No new stack |
| Compliance / privacy | Not affected | Not affected | Not affected |
| Maintainability | The SDK tracks the specification | The types track it; the forwarding is ours | Everything is ours to track |
| Lock-in | On the SDK | On the types package | None |

## More Information

- [Phase 5 preparation](../phases/phase-5-preparation.md), decision P5-5: what was
  read on the official sources, and where
