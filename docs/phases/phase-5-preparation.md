# Phase 5: preparation (A2A and MCP, v0.2)

- **Status**: prepared on 2026-10-02. The owner decided P5-1 to P5-8 on 2026-10-05,
  each with the recommended option: ADR-0046 to ADR-0053. The two checks listed below as
  not verified were made that day: `mcp-types` 2.2.0 depends only on Pydantic and
  `typing-extensions` and holds both eras of the protocol; `a2a-sdk[signing]` 1.2.1
  provides a card verifier that takes a key provider and a list of algorithms
- **Date**: 2026-10-02
- **Inputs**: the brief; [Phase 0](phase-0-analysis.en.md), whose view of the two
  protocols came from secondary sources; the gateway and the toolkit of Phases 3 to 4b
- **Expected output from the project owner**: the decisions below

> Arbiter is a support tool and does not provide legal advice.

## 1. The state of the two protocols, checked on their own sources

Read on 2026-10-02.

### MCP

| Fact | Source |
|---|---|
| The current revision is `2026-07-28`. Revisions are dates; one is current, earlier ones are final | `modelcontextprotocol.io/specification/versioning` |
| The core is stateless: no `initialize` handshake, no protocol session and no `Mcp-Session-Id`. Every request carries its protocol version and the client's capabilities in `_meta`, and on HTTP in the `MCP-Protocol-Version` header | Changelog of `2026-07-28`, major changes 1 and 2 |
| A server must implement `server/discover`, which returns its supported versions, capabilities and identity. A version it does not support is answered with `UnsupportedProtocolVersionError` (`-32022`) listing the ones it does | Versioning page of the revision; changelog, major change 3 |
| Streamable HTTP requests must carry the headers `Mcp-Method` and `Mcp-Name`: an intermediary can see which method and which tool a request is for without parsing the body | Changelog, minor change 4 |
| List and read results carry `ttlMs` and `cacheScope` (`public` or `private`), which says whether a shared intermediary may cache them | Changelog, minor change 5 |
| Server-initiated requests are replaced by multi round-trip requests: a result of type `input_required` that the client answers by retrying | Changelog, major changes 7 and 8 |
| Stream resumability is removed; the HTTP+SSE transport, Roots, Sampling, Logging and Dynamic Client Registration are deprecated | Changelog |
| Authorization: the client must validate `iss` when present (RFC 9207) and keys its credentials by issuer | Changelog, minor changes 7 and 9 |
| Revisions `2025-11-25` and earlier are "legacy": they open with `initialize`. A modern client fails against a legacy server and a legacy client against a modern server; only a "dual-era" implementation talks to both. A dual-era client probes and caches the era per origin | Versioning page, compatibility matrix |
| The Python SDK is `mcp` 2.2.0 on PyPI, Python 3.10 or later, with client, server, stdio, Streamable HTTP and SSE. Its base dependencies include `mcp-types`, Starlette, uvicorn, `httpx2`, PyJWT and the OpenTelemetry API | `pypi.org/pypi/mcp/json`; the README of the SDK |

Not verified: which protocol revisions `mcp` 2.2.0 implements, and whether it is
dual-era. Its README does not say. This is checked on the installed package before
anything is built on it.

### A2A

| Fact | Source |
|---|---|
| The latest released version of the specification is `1.0.0` | `a2a-protocol.org/latest/specification` |
| Three protocol bindings: JSON-RPC, gRPC, HTTP+JSON/REST | Specification, sections 9 to 11 |
| A server must make an Agent Card available. Clients find it at `https://{domain}/.well-known/agent-card.json`, in a registry or catalogue, or by direct configuration | Section 8.1, 8.2 and 14.3 |
| The card lists `supportedInterfaces` in order of preference, each with its binding, URL and protocol version | Section 8.3 |
| A card **may** be signed, with JWS (RFC 7515) over the card canonicalized with JCS (RFC 8785), the `signatures` field and default values left out. A signature has `protected`, `signature` and an optional `header`; the protected header carries `alg`, `kid` and optionally `jku`, the URL of a key set | Section 8.4.1 and 8.4.2 |
| A client **should** verify at least one signature before trusting a card, and must not use expired or revoked keys. It may keep a store of trusted keys | Section 8.4.3 |
| Security schemes: API key, HTTP authentication, OAuth 2.0, OpenID Connect, mutual TLS. The extended card needs authentication | Sections 4.5 and 3.1.11 |
| Eleven operations: send a message (plain and streaming), get, list, cancel and subscribe to a task, four for push notification configurations, and the extended card | Section 3.1 |
| The Python SDK is `a2a-sdk` 1.2.1 on PyPI, Python 3.10 or later. It implements 1.0 with a compatibility mode for 0.3, client and server, on the three bindings. Extras include `signing`, `http-server`, `fastapi`, `grpc`. Base dependencies include protobuf, `google-api-core`, httpx and Pydantic | `pypi.org/pypi/a2a-sdk/json`; the README of the SDK |

Not verified: what the `signing` extra of the SDK provides. Its README does not say.

### What changed against Phase 0

Phase 0 had both right in outline. Two things matter more than it said. A stateless MCP
core means a proxy can govern each request on its own, with the method and the tool name
in headers, but it cannot serve a legacy server or client without becoming a party to a
session. And an A2A card signature is optional and names its own key location (`jku`):
verifying it is only worth something against keys the operator already trusts.

Arbiter already has an RFC 8785 canonicalization of its own, written for the audit chain
(ADR-0029). It refuses floats, which the audit log never holds; an Agent Card may hold
numbers, so its use here has to be checked against the card schema first.

## 2. What Phase 5 is for

The brief asks for an implementation of A2A with a registry of agents, and for a
registry of MCP servers with authorization and logging of every invocation. Phase 0
settled two points: Arbiter governs the protocols through their official SDKs and does
not implement them again, and a catalogue alone cannot log invocations, so the MCP
module needs a proxy in the data path.

The link to the rest of the product is the inventory. An agent and an MCP server belong
to a declared AI system, or to none; what is used and was not declared is a finding, as
for models today.

## 3. Decisions

Each has a recommendation. Azure cost is "none" throughout: nothing here creates a
resource before Phase 6.

### P5-1: Which MCP revisions the proxy speaks

| Criterion | 1. Modern only (`2026-07-28`) | 2. Dual-era on both sides, with translation | 3. Modern, plus pass-through of legacy to legacy without translation |
|---|---|---|---|
| Complexity | Low: one request, one decision | High: sessions, and server-initiated requests turned into multi round-trip ones | Medium: a second, stateful path |
| Scalability | Stateless, any number of replicas | Session affinity | Session affinity for the legacy path |
| Security | One path to reason about | The largest surface | Two paths |
| Compliance / privacy | Every call is seen and audited | The same | The same |
| Maintainability | Follows the current revision | Follows two eras and their mapping | Follows two eras |
| Lock-in | None | None | None |

**Recommendation: 1.** The catalogue still records the revisions each server declares
(`server/discover`), and a server that is legacy only is listed as not governable by the
proxy, which is a finding. Option 3 can be added when a user needs it.

### P5-2: Where the MCP proxy sits

| Criterion | 1. A module of the gateway application, switched on by a server role | 2. A separate application in the same distribution | 3. A separate distribution |
|---|---|---|---|
| Complexity | Low: identity, policy, audit and the database are already there | Medium: a second composition root | High |
| Scalability | Scales with the gateway; the role lets it run alone when needed (ADR-0020) | Independent | Independent |
| Security | One authentication path | Two to keep equal | Two |
| Compliance / privacy | One audit chain per tenant | The same, across processes | The same |
| Maintainability | Good | Duplicated wiring | Two releases |
| Lock-in | None | None | None |

**Recommendation: 1.**

### P5-3: Which MCP transports the proxy serves

| Criterion | 1. Streamable HTTP only | 2. Also stdio servers started by the proxy |
|---|---|---|
| Complexity | Low | High: process supervision |
| Scalability | Good | One process per server per replica |
| Security | No code is started | The proxy runs commands from a catalogue: a way to run arbitrary programs |
| Compliance / privacy | Remote servers are governed | Local servers too |
| Maintainability | Good | Fragile across operating systems |
| Lock-in | None | None |

**Recommendation: 1.** A stdio server can still be declared in the catalogue, as known
and not proxied.

### P5-4: What the MCP side enforces in v0.2

| Criterion | 1. Catalogue only | 2. Catalogue, and a proxy with an allowlist of servers and tools per project and AI system, and an audit entry per call (method, server, tool, sizes, outcome: never the arguments) | 3. As 2, plus detection and redaction of personal data in tool arguments and results |
|---|---|---|---|
| Complexity | Low | Medium | High: results are arbitrary JSON |
| Scalability | Not in the data path | One policy evaluation per call | Detection on every payload |
| Security | Nothing is enforced | Least privilege on tools | The same, plus content |
| Compliance / privacy | Declared use only | Declared against observed, with no content stored | Content is inspected, never stored |
| Maintainability | Good | Good | Detector quality becomes visible here too |
| Lock-in | None | None | None |

**Recommendation: 2**, with 3 as a deferrable item.

### P5-5: How the MCP protocol is handled in code

| Criterion | 1. The official `mcp` SDK, as an extra | 2. The official `mcp-types` package for the messages, and Arbiter's own forwarding over the HTTP client it already has | 3. Arbiter's own models and forwarding |
|---|---|---|---|
| Complexity | Medium: an SDK built for clients and servers, used as a proxy | Low to medium | Medium |
| Scalability | Unknown until measured | The proxy forwards bytes | The same |
| Security | A second HTTP stack (`httpx2`, Starlette, uvicorn) in the data path | No new stack | No new stack |
| Compliance / privacy | Not affected | Not affected | Not affected |
| Maintainability | The SDK tracks the specification | The types track it; the forwarding is ours | Everything is ours to track |
| Lock-in | On the SDK | On the types package | None |

**Recommendation: 2, subject to a check.** `mcp-types` was seen only as a dependency of
`mcp`; what it contains is checked first, and if it is not usable on its own the choice
falls back to 1, as an optional extra. The mock MCP server of the tests and of the demo
uses the official SDK either way.

### P5-6: What Arbiter adds to A2A

| Criterion | 1. A registry of agents with verified cards, and findings | 2. As 1, plus authorization and a proxy for the JSON-RPC and HTTP+JSON bindings, with an audit entry per call | 3. As 2, plus gRPC |
|---|---|---|---|
| Complexity | Low to medium | High: streaming and task subscriptions | Very high |
| Scalability | Not in the data path | A second proxied protocol | The same |
| Security | Cards are checked; calls are not seen | Calls are authorized | The same |
| Compliance / privacy | Declared agents; undeclared use is invisible | Declared against observed | The same |
| Maintainability | Good | Follows the SDK | A third binding |
| Lock-in | None | On the SDK | On the SDK |

**Recommendation: 2, in two steps**: the registry and the card verification first, then
the proxy. gRPC is not proxied; an agent that offers only gRPC is listed as not
governable.

### P5-7: How the A2A protocol is handled in code

| Criterion | 1. The official `a2a-sdk`, as an extra, behind a port, in `adapters` | 2. Arbiter's own models |
|---|---|---|
| Complexity | Medium | High: eleven operations and three bindings |
| Scalability | Not affected | Not affected |
| Security | A maintained implementation | Ours to get right |
| Compliance / privacy | Not affected | Not affected |
| Maintainability | Tracks 1.0 and the 0.3 compatibility mode | Ours to track |
| Lock-in | On the SDK, contained by the port | None |

**Recommendation: 1.** The base install stays free of it: protobuf and
`google-api-core` come only with the extra.

### P5-8: Which keys a card signature is verified against

| Criterion | 1. Keys the operator configured, by key id; `jku` is ignored | 2. As 1, and `jku` is followed over HTTPS for domains on an allowlist | 3. `jku` is followed wherever it points |
|---|---|---|---|
| Complexity | Low | Medium | Low |
| Scalability | No request is made | One request per key set, cached | The same |
| Security | Only trusted keys | Trust by domain; requests leave the server to listed hosts only | A card vouches for itself, and the server fetches any URL a card names |
| Compliance / privacy | A verified card means something | The same | It means nothing |
| Maintainability | Keys are rotated by hand | Rotation follows the key set | The same |
| Lock-in | None | None | None |

**Recommendation: 1**, with 2 as a later step. An unsigned card, or one signed with an
unknown key, is registered as unverified and reported as a finding; whether such an agent
may be called is a policy rule.

## 4. Not decisions, but worth knowing before answering

- The demo of the phase uses mock agents and a mock MCP server. No real model is involved
  (ADR-0033).
- New findings follow from the decisions: an MCP server or an agent in traffic that the
  catalogue does not hold; a tool called that the allowlist does not name; an unverified
  card; a legacy-only server.
- Two new optional extras (`mcp` or `mcp-types`, and `a2a-sdk`) change the dependencies,
  so the container check runs again and the lock file changes.
- Which JWS library verifies the signatures is settled while implementing, after reading
  what the `signing` extra of the A2A SDK provides.

---

*Arbiter is a support tool and does not provide legal advice.*
