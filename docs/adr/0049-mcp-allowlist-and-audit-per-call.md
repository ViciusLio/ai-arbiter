---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0049: The MCP side enforces an allowlist of servers and tools, and audits every call without its arguments

## Context and Problem Statement

The brief asks for a registry of MCP servers with authorization and logging of every invocation. A catalogue alone sees no invocation.

## Considered Options

- **1.** Catalogue only
- **2.** Catalogue, and a proxy with an allowlist of servers and tools per project and AI system, and an audit entry per call (method, server, tool, sizes, outcome: never the arguments)
- **3.** As 2, plus detection and redaction of personal data in tool arguments and results

## Decision Outcome

Chosen option: **2**.

A catalogue of servers, and a proxy that allows a call only when the server and the tool are allowed for the project and the AI system of the key. Each call is one audit entry with the method, the server, the tool, sizes and the outcome. Arguments and results are never stored. Detection and redaction of personal data in arguments and results is a deferrable item.

### Consequences

- Good: least privilege on tools, and declared against observed for MCP as for models.
- Bad: content passes through uninspected in v0.2.

## Pros and Cons of the Options

| Criterion | 1. Catalogue only | 2. Catalogue, and a proxy with an allowlist of servers and tools per project and AI system, and an audit entry per call (method, server, tool, sizes, outcome: never the arguments) | 3. As 2, plus detection and redaction of personal data in tool arguments and results |
|---|---|---|---|
| Complexity | Low | Medium | High: results are arbitrary JSON |
| Azure cost | None | None | None |
| Scalability | Not in the data path | One policy evaluation per call | Detection on every payload |
| Security | Nothing is enforced | Least privilege on tools | The same, plus content |
| Compliance / privacy | Declared use only | Declared against observed, with no content stored | Content is inspected, never stored |
| Maintainability | Good | Good | Detector quality becomes visible here too |
| Lock-in | None | None | None |

## More Information

- [Phase 5 preparation](../phases/phase-5-preparation.md), decision P5-4: what was
  read on the official sources, and where
