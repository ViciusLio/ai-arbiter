# Phase 5: A2A and MCP

- **Status**: implemented and approved by the project owner on 2026-10-05. Done after
  the approval, so not in the text below: the A2A proxy joined to the client and a
  server of the official SDK (I-45), and `tools/list` filtered to what the caller may
  call (part of I-41)
- **Date**: 2026-10-05
- **Inputs**: [Phase 5 preparation](phase-5-preparation.md) (the two protocols checked on
  their own sources, decisions P5-1 to P5-8), ADR-0046 to ADR-0055, the gateway and the
  toolkit of Phases 3 to 4b
- **Expected output from the project owner**: approval of the phase, and what comes
  next: Phase 6 (Azure), which needs a subscription and a budget (ADR-0008), or the
  improvements listed below
- **Target release**: `0.2.0`. Not tagged, not published; the version is still `0.1.0a1`

> Arbiter is a support tool and does not provide legal advice. Nobody with legal training
> has reviewed the rule pack.

## Decisions

| ADR | Decision |
|---|---|
| [0046](../adr/0046-mcp-proxy-speaks-the-modern-revision.md) | The MCP proxy speaks revision `2026-07-28` only |
| [0047](../adr/0047-mcp-proxy-as-a-gateway-module.md) | The MCP proxy is a module of the gateway application, switched on by a role |
| [0048](../adr/0048-mcp-streamable-http-only.md) | Streamable HTTP only; the proxy never starts a process |
| [0049](../adr/0049-mcp-allowlist-and-audit-per-call.md) | An allowlist of servers and tools, and an audit entry per call without its arguments |
| [0050](../adr/0050-mcp-official-types-own-forwarding.md) | MCP messages from the official types package; Arbiter's own forwarding |
| [0051](../adr/0051-a2a-registry-then-proxy.md) | A2A: a registry with verified cards, then a proxy for JSON-RPC and HTTP+JSON |
| [0052](../adr/0052-a2a-official-sdk-behind-a-port.md) | A2A through the official SDK, as an extra, behind a port |
| [0053](../adr/0053-a2a-card-signatures-against-configured-keys.md) | Card signatures verified only against keys the operator configured |
| [0054](../adr/0054-no-cache-of-key-lookups.md) | API keys and roles are read on every request, not cached |
| [0055](../adr/0055-semantic-pii-detection-as-an-optional-plugin.md) | Personal data written in words is detected by an optional local plugin |

Choices made while implementing, within those decisions, that the owner may want to
revisit:

- **What a grant on an MCP server covers.** Listing what a server offers needs any
  grant; calling a tool needs a grant for that tool; anything else, reading a resource
  for example, needs a grant for the whole server.
- **A proxy never follows a redirect**, so that a server or an agent cannot send a
  request, with its credential, where the catalogue never pointed.
- **An agent's interface counts only on the host its card was read from.**
- **An unsigned card does not stop a call by default**, because A2A makes signing
  optional; a card whose signature fails does. The rule is data and can be tightened.
- **Push notification configurations are not created through the A2A proxy**: they would
  have the agent send updates to an address around it.
- **Both proxies fail closed**: a call whose decision cannot be written to the audit log
  is not forwarded, whatever `audit.fail_mode` says for the model gateway.
- **Group affiliations are off by default** in the semantic detector: measured, six
  detections in ten were ordinary adjectives.

## Tasks

| # | Task | Result |
|---|---|---|
| 1 | MCP catalogue | Servers, the names of their tools, grants to the tenant, a project or an AI system; `arbiter mcp`, `/api/v1/mcp` |
| 2 | MCP proxy | `POST /mcp/{server}`: the request is checked against its mirrored headers, decided by a rule pack, written to the audit log and to the table `invocation`, then forwarded with the credential of the catalogue. Discovery of a server's revisions and tools |
| 3 | A2A registry | Agents registered by the address of their card; the card read over https and verified against trusted keys, through the official SDK behind a port; `arbiter a2a`, `/api/v1/a2a` |
| 4 | A2A proxy | `POST /a2a/{agent}` (JSON-RPC) and `/a2a/{agent}/rest/...` (HTTP+JSON), for the operations A2A 1.0 defines; the same decide, record, forward as for MCP |
| 5 | Findings | Seven scan rules about servers, agents and calls, read through a new port, `TargetDirectory`; scan pack `2026.10.2`, 21 rules |
| 6 | Semantic detection of personal data | Plugin `presidio` on Presidio and spaCy, added to the built-in detectors; a measurement script and its published figures |
| 7 | Guided demonstration | `arbiter demo tour`: gateway, both proxies, scan and audit in one process, with stand-ins |
| 8 | Presentation | A deck for people who are not developers, in Italian and in English |

## Defects found while building

- Short ids on the command line were the first characters of an id, which are a
  timestamp: two budgets or two grants created together looked the same. Found by a test
  of the MCP grants; fixed for budgets and grants, as findings already did.
- The response of an upstream server was relayed raw, which would have passed on
  compressed bytes without saying so. It is now relayed decoded.
- A test of the MCP protocol needed an HTTP library that the install without extras
  does not have; CI found it.
- Two scenarios and, later, the guided demonstration sent traffic for the same systems:
  the scanner, rightly, reported it and a scenario no longer got what it expects. The
  demonstration now has two systems of its own.
- Each instance of the semantic detector loaded the language models again; a few
  instances exhausted the memory of the development machine. The models are now loaded
  once per process and shared.
- A language model reading a text in another language marked ordinary words as names.
  A text now goes to the model of its language only.

## What was verified

The full check, `scripts/check.sh --containers`, was run on 2026-10-05 in the dev
container, on the code of commit `1d653b9`; the commits after it changed documentation
and the Pages workflow only.

| Check | Result |
|---|---|
| Lint, format, types (strict), import rules | Pass; 4 contracts kept |
| Tests with coverage, Python 3.12, SQLite and PostgreSQL | 1132 passed, 4 skipped; 97% coverage |
| Tests, Python 3.13 and 3.14 | 1128 passed, 8 skipped, on each |
| Tests without extras | 683 passed, 208 skipped |
| Latency added to a request, mock provider, one request at a time | About 20 ms on SQLite and 19 ms on PostgreSQL (mean), as in Phase 3 |
| Image build; the image runs as a non-root user; Compose stack; health; a request and the audit chain | Pass |
| Digest sent to the mail catcher of the stack | Pass |
| The three scenarios, in the container | Pass |
| The guided demonstration, in the container | Seven steps, each as expected; audit chain of 68 entries without a broken link |
| MCP proxy between the client and a server of the official SDK, in process | Pass, in the test suite |
| GitHub Pages | The three addresses answer 200 and the rest of the repository 404, after the first run of the workflow |

Not verified:

- the A2A proxy with the client and a server of the official SDK (I-45), and a card
  read from a real agent over the network (I-43);
- an MCP server or client of another vendor, and either proxy over a real network;
- the semantic detector on real prompts: the figures come from invented sentences;
- the presentations in a browser: only the build script and the answers of the site;
- CI on the last commit of the phase, at the time this summary was written;
- what was already not verified before the phase: the legal correctness of the rule
  pack, the Azure OpenAI adapter, the release workflow.

## Limits

- The MCP proxy speaks one revision and one transport, does not inspect the content of a
  call, and shows every tool in `tools/list`, also the ones the caller may not call.
- The A2A proxy was tested against a stand-in agent written from the specification: the
  client and the server of the official A2A SDK have not gone through it (I-45). gRPC is
  not proxied. The proxy serves no card of its own.
- Cards are read on request, not on a schedule.
- The measurement of the detectors uses about fifty invented sentences per language,
  written by the author of the detectors. Health data is found by no detector.
- The presentation was not viewed in a browser by its author.

---

*Arbiter is a support tool and does not provide legal advice.*
