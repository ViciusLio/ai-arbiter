---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0048: The MCP proxy serves Streamable HTTP only

## Context and Problem Statement

MCP has two standard transports: stdio, where the client starts the server as a local process, and Streamable HTTP.

## Considered Options

- **1.** Streamable HTTP only
- **2.** Also stdio servers started by the proxy

## Decision Outcome

Chosen option: **1**.

The proxy forwards Streamable HTTP. A stdio server can be declared in the catalogue, as known and not proxied. The proxy never starts a process.

### Consequences

- Good: a catalogue entry cannot become a way to run a program on the server.
- Bad: local servers are visible only as declarations until the local agent exists.

## Pros and Cons of the Options

| Criterion | 1. Streamable HTTP only | 2. Also stdio servers started by the proxy |
|---|---|---|
| Complexity | Low | High: process supervision |
| Azure cost | None | None |
| Scalability | Good | One process per server per replica |
| Security | No code is started | The proxy runs commands from a catalogue: a way to run arbitrary programs |
| Compliance / privacy | Remote servers are governed | Local servers too |
| Maintainability | Good | Fragile across operating systems |
| Lock-in | None | None |

## More Information

- [Phase 5 preparation](../phases/phase-5-preparation.md), decision P5-3: what was
  read on the official sources, and where
