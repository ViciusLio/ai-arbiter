# Arbiter

**AI governance gateway and EU AI Act compliance toolkit.**

Arbiter links what AI systems an organisation *says* it runs, as an inventory classified
under the EU AI Act, with what its traffic *shows* it runs. A gateway produces the
evidence and enforces constraints derived from the classification; a compliance toolkit
turns the evidence into classified systems, findings and a daily digest. Either half works
without the other.

> **Status: alpha, not released yet.** Both halves work end to end. The gateway: an
> OpenAI-compatible endpoint with policy, redaction of personal data, routing, metering,
> budgets and a hash-chained audit log. The compliance toolkit: an inventory of AI
> systems, an indicative AI Act classification that a person reviews, findings, discovery
> of systems nobody declared, reports and a daily digest that can be sent by e-mail. See
> the [roadmap](#roadmap).

> Arbiter is a support tool. It does not provide legal advice.

**New here, and not a developer?** Open the presentation:

- in English: <https://viciuslio.github.io/ai-arbiter/arbiter.en.html>
- in Italian: <https://viciuslio.github.io/ai-arbiter/arbiter.it.html>

Each is one self-contained file, also in [`docs/presentation/`](docs/presentation/). The site
holds the presentations and nothing else of the repository.

## Where the project is

Updated at every commit. Last update: 2026-10-05.

| Phase | State |
|---|---|
| 0 Analysis, 1 Architecture, 2 Scaffolding | Done |
| 3 Gateway MVP | Done |
| 4 Compliance MVP | Done |
| 4b Deferrable items of v0.1 | Done: importers, reports, digest by e-mail, discovery, scenarios ([summary](docs/phases/phase-4b-deferrable-items.md)) |
| Improvements after Phase 4b | Done for what needed no decision: see the [tracking table](#release-improvement-tracking) |
| 5 A2A and MCP (v0.2) | **Built, being closed**: every step below is done except the full check of the phase; then it waits for the owner's approval |
| 6 Azure (v0.3) | Not started |
| 7 Documentation and packaging (v1.0) | Not started |

Phase 5, step by step:

| Step | State |
|---|---|
| Check A2A and MCP on their official sources ([preparation](docs/phases/phase-5-preparation.md)) | Done |
| Decisions P5-1 to P5-8, and the one on key lookups | Done: ADR-0046 to ADR-0054 |
| MCP catalogue: servers and their tools, tied to declared AI systems | Done: `arbiter mcp servers` and `mcp grants`, `/api/v1/mcp`, an allowlist that allows nothing by default. Nothing forwards a call yet |
| MCP proxy: Streamable HTTP, revision `2026-07-28`, allowlist of servers and tools, an audit entry per call | Done: `POST /mcp/{server}`; decide, record, then forward. Tested with the client and a server of the official SDK, in process |
| A2A registry: agent cards fetched, stored and verified against configured keys | Done: `arbiter a2a agents` and `a2a grants`, `/api/v1/a2a`; a card is verified only against `a2a.trusted_keys`, and an interface counts only on the host of the card. Tested with cards signed by the official SDK, not with a real agent on the network |
| A2A proxy for the JSON-RPC and HTTP+JSON bindings, with authorization and audit | Done: `POST /a2a/{agent}` and `/a2a/{agent}/rest/...`; decide, record, then forward. Tested against a stand-in agent, not with the SDK's client or a real agent |
| Findings: undeclared servers and agents, tools outside the allowlist, unverified cards, legacy-only servers | Done: seven rules in the scan pack `2026.10.2`, read through a port from the catalogues and from the recorded calls |
| A presentation for people who are not developers, in Italian and in English | Done: `docs/presentation/`, a deck read from left to right, one screen per section. The English page is built from the Italian one by `scripts/build_presentation_en.py`. Not viewed in a browser by its author |
| Semantic detection of personal data: an optional plugin on Presidio, with measured precision and recall (ADR-0055) | Done: plugin `presidio`, extra `pii`, figures in `docs/pii-evaluation.md` |
| A guided demonstration: gateway, toolkit, a mock MCP server and a mock agent | Done: `arbiter demo tour`, seven steps in one process, about a minute, repeatable; covered by a test |
| Phase summary and the full check, containers included | Not started |

Before `0.1.0`, and not in the hands of the code: a review of the AI Act rule pack by a
person with legal training (ADR-0041), and a comparison of the quoted articles with
EUR-Lex (ADR-0034). No release has been published.

Nothing is published yet. The name of this project on PyPI will be **`ai-arbiter`**. It
is not related to `arbiter-ai` or `arbiter`, which are different projects by other
authors and are already on PyPI.

## Install

Not on PyPI yet. Once the first release, `0.1.0a1`, is published:

```bash
pip install --pre ai-arbiter      # --pre until 0.1.0: the first release will be an alpha
```

Or run it without installing:

```bash
uvx ai-arbiter@0.1.0a1 --version
```

Until then, install from a clone: `uv sync --all-extras`, then `uv run arbiter`.

The base install is the offline toolkit and CLI, on SQLite. The HTTP gateway is an extra
(from a clone, `uv sync --all-extras` already includes it):

```bash
pip install --pre "ai-arbiter[gateway]"   # once published
```

## Try it

From a clone, put `uv run` in front of each command below: until the first release there
is no installed `arbiter` command. No Docker and no cloud account needed. The mock
provider answers in place of a real
model.

```bash
arbiter init                                   # arbiter.yaml, a SQLite database, secrets in .env
arbiter keys create --name demo --role admin   # prints an API key, once
arbiter serve                                  # http://127.0.0.1:8080, API docs at /docs
```

In another terminal, with the key from the second command:

```bash
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer arb_..." -H "Content-Type: application/json" \
  -d '{"model": "mock-small", "messages": [{"role": "user", "content": "Write to mario.rossi@example.com"}]}'

arbiter usage report        # what was used and its estimated cost; --locale it for Italian
arbiter budgets create --limit 50 --hard   # a monthly limit on the tenant; budgets list
arbiter mcp servers add files --name "File tools" --url https://tools.example.org/mcp   # the MCP catalogue
arbiter mcp grants add files --tool read          # then clients call http://127.0.0.1:8080/mcp/files
arbiter a2a agents add routes --name "Route planner" --card-url https://agent.example.org/.well-known/agent-card.json
arbiter audit verify        # recomputes the hash chain of the audit log
arbiter pii detectors       # what is detected in prompts, and what is not
```

The response header `X-Arbiter-Redacted: email` says the address was replaced before the
prompt left the gateway. Nothing of the prompt is stored.

Then the compliance side, with seven invented systems (from a clone of the repository):

```bash
arbiter systems apply -f examples/systems.yaml   # declare and classify
arbiter systems show cv-screening                # indicative tier, obligations, provisions, dates
arbiter scan                                     # declarations against classification and traffic
arbiter findings list
arbiter digest run --locale it                   # the daily digest, here in Italian
arbiter report system cv-screening               # everything recorded about one system
arbiter report audit --format html -o out/       # the audit log of the last 30 days
arbiter ingest examples/litellm-logs.jsonl --source litellm   # records of another gateway
arbiter systems discover                         # what in the traffic nobody declared
arbiter demo tour                                # the guided demonstration: gateway, tools, agents, scan, audit
arbiter demo run --all                           # three invented scenarios, in the tenant "demo"
```

Any client that speaks the OpenAI API works: point its base URL at
`http://127.0.0.1:8080/v1` and use the Arbiter key as the API key.

The command is `arbiter`; `ai-arbiter` is an alias for it.

## What the gateway does

| Capability | In short |
|---|---|
| Identity | Teams, projects, principals, API keys stored as keyed hashes, three roles |
| Policy | Rules as data: model allowlist, hard budgets, redaction. A denial explains itself |
| Redaction | Personal data and credentials in prompts are masked before the provider sees them: formats by default, names and places too with an optional local plugin |
| Routing | Deployments ordered by priority or cost, with retry and fallback |
| FinOps | Tokens and estimated cost per tenant, team, project, principal and AI system; soft and hard budgets, set over HTTP or from the command line |
| Audit | One hash chain per tenant, verifiable and exportable; no content, no names |
| Providers | OpenAI-compatible endpoints, Azure OpenAI, and a mock |
| MCP catalogue and proxy (Phase 5, in progress) | The MCP servers an organisation knows and who may call which tool; a proxy that forwards a call only when a grant allows it and records every call without its arguments |
| A2A registry and proxy (Phase 5, in progress) | The agents an organisation calls: what their Agent Card says, whether a key the operator trusts signed it, who may call them; a proxy for the JSON-RPC and HTTP+JSON bindings that forwards a call only when a grant allows it and records every call without what was said |

How to configure and use each of them: [the gateway](docs/gateway.md) and
[the audit log](docs/audit.md).

## What the compliance toolkit does

| Capability | In short |
|---|---|
| Inventory | AI systems declared in YAML, through the API or the CLI, with their AI Act roles |
| Classifier | Deterministic rules as data, written from the Official Journal text: out of scope, prohibited, high-risk, transparency, minimal. Each outcome cites its provision and the date it applies from |
| Review | A classification is indicative until a named person confirms or overrides it |
| Scanner | Twenty-one rules compare what was declared with the classification and with the traffic, name the projects whose requests no declared system accounts for, and report MCP servers and A2A agents that cannot be governed, cards that are not verified and calls that no grant or no catalogue covers |
| Findings | Deduplicated, reviewed, accepted with an expiry or suppressed with a reason; all audited |
| Discovery | Requests that belong to no declared system are grouped by project and proposed as candidate systems, with a draft declaration for a person to complete |
| Importers | Records of another gateway (LiteLLM, or Arbiter's own JSON lines) are imported without their content and scanned like the gateway's own |
| Digest | Inventory, findings, traffic and the audit head, in Markdown and HTML, in English and Italian; sent by e-mail to each recipient in their language |
| Reports | Everything recorded about one system, and the audit log over a period; Markdown and HTML that prints well |
| Demonstration | `arbiter demo tour` walks through the gateway and the toolkit in one command; three scenarios of invented systems and traffic, each with the outcome it expects |
| Link to the gateway | A system classified as a prohibited practice gets no model; routing can be limited by risk tier |

How it works and what it does not cover: [the compliance toolkit](docs/compliance.md).

### Limits you should know

- **A classification is indicative, not a legal conclusion.** It follows from the facts
  you declare; nothing checks that they are true. The rule pack covers the obligations
  of deployers, not of providers, and not general-purpose AI models. It was written from
  the Official Journal text; its comparison with EUR-Lex by the project owner is still
  pending, and every output says so.
- **Detection of personal data is by format by default.** The built-in detectors find
  e-mail addresses, phone numbers (international and Italian), IBANs, payment cards,
  Italian fiscal codes and VAT numbers, IP addresses and common credential formats. An
  optional local plugin adds names and places written in words (ADR-0055). On about
  fifty invented sentences per language it raised recall from 14-17% to 81-93%, with a
  precision of 93-97% ([figures and limits](docs/pii-evaluation.md)). Neither finds
  dates of birth or health data, and no figure here is a promise about your prompts.
- **Costs are estimates**, computed from a price catalogue you fill in. Arbiter ships no
  prices for real providers.
- **The audit log is tamper-evident, not tamper-proof.** Someone who can write to the
  database can rewrite the whole chain; keep a copy of the head elsewhere.
- **Provider adapters.** The OpenAI-compatible adapter was checked by hand against one
  local server (Ollama); the Azure OpenAI adapter only against a simulated transport.
  Neither has been run against a hosted service.
- **Importers.** The LiteLLM importer follows the format LiteLLM documents. It has not
  read the output of a live LiteLLM.
- **Discovery is as fine as a project.** A project that runs several systems shows as
  one candidate, and nothing is declared for you.
- **E-mail.** The SMTP notifier was checked against a mail catcher over plain SMTP.
  STARTTLS, TLS and authentication are covered by tests that replace the client, not by
  a server. The default notifier writes files and sends nothing.
- **No PDF.** Reports are Markdown and HTML; print the HTML from a browser.
- **MCP proxy.** It speaks revision `2026-07-28` over Streamable HTTP only and does not
  inspect the content of a call. It was tested with the client and a server of the
  official Python SDK, joined in process; no server or client of another vendor, and
  nothing over a real network, has gone through it yet.
- **A2A.** A signature counts only against keys you configured; signing is optional in
  A2A, so many cards will be `unsigned`, and by default that does not stop a call. gRPC
  is not proxied. The proxy was tested against a stand-in agent written from the
  specification: no real agent and no client of the SDK has gone through it yet.

## Configuration

One settings tree, validated at startup. Precedence, highest first:

1. environment variables: prefix `ARBITER_`, nested keys joined by `__`
   (for example `ARBITER_DATABASE__URL`);
2. `arbiter.yaml`, or the file named by `--config` or `ARBITER_CONFIG`;
3. built-in defaults.

Secrets are never written in configuration. They are referenced as `secret://NAME` and
resolved by the active secret store; the default one reads `ARBITER_SECRET_NAME` from the
environment, then from `.env` in the working directory. `arbiter init` generates the
secrets a local workspace needs in `.env`; keep that file out of version control.

## Development

The quickest way to a complete environment is the dev container in `.devcontainer/`:
open the repository in GitHub Codespaces, or with any Dev Container tool, and you get
Python 3.12, 3.13 and 3.14, uv, Docker and a PostgreSQL test database.

Without it, you need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/):

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
```

`scripts/check.sh` runs all of the above on every supported Python version and measures
the latency the gateway adds; `scripts/check.sh --containers` also builds the image,
starts the Compose stack, sends a request through it, sends the digest to the mail
catcher of the stack and runs the scenarios in the container.

Tests run on SQLite by default. To run them on PostgreSQL as well, set
`ARBITER_TEST_DATABASE_URL` to an empty database; the dev container does this for you.

A container image and a Compose file are in `deploy/`.

## Roadmap

| Version | Content |
|---|---|
| 0.1 | Gateway MVP (OpenAI-compatible proxy, FinOps metering, policy, audit log) and compliance MVP (inventory, AI Act classifier, findings, daily digest, CLI), with importers, discovery, reports, e-mail delivery and scenarios: **built, not released**. `0.1.0` waits for a legal review of the rule pack |
| 0.2 | A2A and MCP: agent registry with verified cards, governed MCP catalogue and proxy, multi-agent demo: **built, not released**; the phase waits for its full check and for approval. The proxies were tested against stand-ins and, for MCP, the official SDK; not against real servers or agents on a network |
| 0.3 | Azure: Bicep, Container Apps, Entra ID, observability, hardening |
| 1.0 | Documentation, quickstart, demo scenarios |

Design and decisions are in [`docs/architecture`](docs/architecture/README.md) and
[`docs/adr`](docs/adr/README.md).

## Release improvement tracking

At the end of each phase the project records where it stands, strengths and weaknesses
alike, and what would improve it. Rows stay in the table after they are closed.

### Where each phase stands

The first two columns are what was written when each phase closed and are kept as
written. The last column says what has changed since, as of 2026-10-05.

| Phase | Strengths, at the end of the phase | Weaknesses, at the end of the phase | What changed since |
|---|---|---|---|
| 0: Analysis | The scope is one end-to-end slice with a core and deferrable parts, decided before any code. The positioning is clear: link the inventory classified under the AI Act with real traffic | AI Act dates come from secondary sources. The analysis is in Italian, the rest of the documentation in English | The dates were checked in Phase 4 against the Official Journal texts and are in the rule pack with their provisions. Still open: the owner's comparison with EUR-Lex |
| 1: Architecture | 26 decision records with option tables. Module boundaries, data model, interfaces and a first threat model are written down | No prototype was built, so the interfaces are untested. Default PII detection has low recall on names and free text. The audit chain is tamper-evident, not tamper-proof | The interfaces were built in Phases 2 to 4b; where the code differs from the sketches is listed in `docs/architecture/interfaces.md`. In Phase 5 the detection was measured (`docs/pii-evaluation.md`): the default detectors find 14 to 17% of the personal data in the test sentences, the optional plugin `presidio` 81 to 93% (ADR-0055). Still true: the default install misses names and free text, and the chain is tamper-evident only (external anchoring is deferrable) |
| 2: Scaffolding | Every check passes on Python 3.12, 3.13 and 3.14, on SQLite and PostgreSQL, with 98% coverage. The image and the Compose stack run. CI is green on Linux and Windows | The release workflow has never run and `0.0.1` is not published. No product feature exists yet. Telemetry is limited to a tracer bootstrap | Product features exist since Phases 3 and 4. `0.0.1` was replaced by `0.1.0a1` (ADR-0032). Still true: the release workflow has never run, nothing is published, and nothing is instrumented beyond the tracer bootstrap |
| 3: Gateway | A request goes end to end: key, policy, redaction, routing, metering, audit. Every outcome is an explained decision in a verifiable chain. No prompt text is stored, and a test searches the whole database to prove it. The same tests run on SQLite and PostgreSQL. Decisions were taken before the code and recorded (ADR-0027 to ADR-0031) | The adapters for real providers were never run against one. PII detection misses names and free text, and its precision and recall are not measured. About 20 ms and 17 database statements are added to each request, and the requests of one tenant queue on its audit chain. Nothing is instrumented yet. Deferrable items of ADR-0009 are not started | The OpenAI-compatible adapter was checked against a local model server (ADR-0033). Routing by risk tier came in Phase 4; importers, reports, e-mail, discovery and scenarios in Phase 4b. Precision and recall of the PII detectors were measured in Phase 5, on a small set (I-13). Still true: the Azure OpenAI adapter never met a real endpoint, the latency and the queue on the audit chain are as measured then. Still deferrable: post-call policy, external anchoring, the opt-in content store, further PII detectors |
| 4: Compliance | The product's idea is now real: a declared system gets an indicative tier with the provision and the date behind every outcome, traffic that contradicts the declaration becomes a finding, and the classification steers the gateway. An unanswered question is never read as "no". Nothing is presented as settled until a person reviewed it. The rule pack was written from the Official Journal text, pinned by checksum. The six acceptance steps of v0.1 run in under a minute | The rule pack has not been read by a lawyer, and its comparison with EUR-Lex is pending. Only deployer obligations are covered. A classification is as good as the declared facts. The questions are summaries written by hand in two languages. Thirteen scan rules. No discovery from traffic, no importers, no reports, no e-mail delivery: the deferrable items of ADR-0009 | Importers, reports, e-mail delivery and discovery were built in Phase 4b; the scan rules are 21 since Phase 5. Still true: no lawyer has read the rule pack, and `0.1.0` waits for that (ADR-0041); the comparison with EUR-Lex is pending; only deployer obligations are covered; a classification is as good as the declared facts |
| 4b: Deferrable items | The comparison of declared with observed now reaches traffic that did not go through Arbiter: records of another gateway are imported without their content, and what belongs to no declared system is named as a candidate, per project. Two reports and the digest by e-mail give something to hand to people outside the tool. Three scenarios show the toolkit on invented data and fail a test when a rule changes an outcome. Nothing is declared, sent or classified without a person: a candidate is a draft, the default notifier writes files | The LiteLLM importer was never run against a live LiteLLM. A candidate is as coarse as a project, and one from imported records stays for 30 days after its system is declared. The SMTP notifier met a server only without encryption and without authentication. The scenarios are few and were written by the author of the rules. No PDF. Discovery and sending exist on the command line only | Approved by the owner on 2026-10-02. The improvements made afterwards are in the table below |
| 5: A2A and MCP | The same control now covers what an AI system reaches beyond a model: a call to an MCP tool or to an A2A agent is decided by rules that are data, written to the audit log and to its own table before it is forwarded, and never forwarded when that record cannot be written. The caller's key never leaves Arbiter: the credential of the catalogue is used, and no redirect is followed. Agent cards are verified only against keys the operator configured. Seven scan rules read the catalogue and the calls. The MCP proxy was joined to the client and a server of the official SDK in the test suite. Personal data written in words is found by an optional plugin, with published figures. A guided demonstration runs the whole product in one command | The A2A proxy met only a stand-in agent written from the specification, and no card was read from a real agent over the network. The MCP proxy speaks one revision and one transport, does not look inside a call and shows every tool in `tools/list`. gRPC is not proxied. Cards are read on request only. The PII measurement rests on about fifty invented sentences per language, written by the author of the detectors; health data is found by no detector. The presentation was not viewed in a browser by its author | Waits for the owner's approval. Open: I-41 to I-47 |

### Improvements

| ID | Phase | Improvement | Why | Target | Status |
|---|---|---|---|---|---|
| I-01 | 0 | Verify AI Act dates and the amending regulation on EUR-Lex, article by article | The rule pack must rest on the official text | Before Phase 4 | Done against the Official Journal texts from the Publications Office: dates and act number confirmed. A spot check on EUR-Lex itself is pending with the owner |
| I-02 | 0 | Add an English summary of the Phase 0 analysis | One language across the documentation | 1.0 | Done after Phase 4b: `docs/phases/phase-0-analysis.en.md`, a summary; the Italian text stays the reference |
| I-03 | 1 | Revise `interfaces.md` and `data-model.md` against the code at the end of Phase 3 | The design was never prototyped and will drift | End of Phase 3 | Done: both documents list where the code differs |
| I-04 | 1 | Publish precision and recall of each PII detector; offer Presidio as a plugin | Users must see what the default detection misses | 0.1.x | Done in Phase 5 with another choice than Presidio alone: precision and recall are published in `docs/pii-evaluation.md`, and Presidio is offered as the optional plugin `presidio`, added to the built-in detectors (ADR-0055) |
| I-05 | 1 | Anchor the audit chain head outside the database, then sign checkpoints | A full rewrite of the chain is otherwise undetectable | 0.1.x, then 0.3 | Open |
| I-06 | 2 | Publish the first release, `0.1.0a1`, and exercise the release workflow | Reserves the name on PyPI; the workflow is unverified | When the owner decides | Open: `0.0.1` is skipped (ADR-0032) |
| I-07 | 2 | Set the PostgreSQL test URL in the CI job that tests the base install | That job missed a defect the dev container found | Phase 3 | Done |
| I-08 | 2 | Review the CodeQL alert list | The workflow passes, the alerts were never read | Phase 3 | Open |
| I-09 | 2 | Give each CI job its own uv cache key; pin the runner image | Jobs race to save one cache; `ubuntu-latest` changes on 19 October 2026 | Phase 3 | Done: `ubuntu-24.04`, one cache per job |
| I-10 | 2 | Add metrics, log export and request-path instrumentation | Only tracing is bootstrapped | 0.1.x, then 0.3 | Open: not done in Phase 3 |
| I-11 | 2 | Reduce the image size (316 MB) | Faster pulls and cold starts | 0.3 | Open |
| I-12 | 3 | Run the OpenAI-compatible and Azure OpenAI adapters against real endpoints | They were tested against a simulated transport only | Before 0.1.0; Azure in Phase 6 | Partly done: `openai_compat` checked by hand against a local Ollama server (ADR-0033). Hosted services and Azure OpenAI still open |
| I-13 | 3 | Measure precision and recall of the PII detectors on a labelled set | Redaction is on by default and its error rates are unknown | 0.1.x, with the simulation scenarios | Partly done in Phase 5: `scripts/measure_pii.py` measures both detectors on `evaluation/pii/` (about fifty invented sentences per language). The set is small and written by the author of the detectors; a larger one, written by someone else, is still needed |
| I-14 | 3 | Add the deferred detectors: identity documents, phone and VAT formats of other member states | Coverage promised by ADR-0014, deferred by ADR-0027 | 0.1.x | Open |
| I-15 | 3 | Reduce the statements on the request path: one statement for the roll-ups, one audit entry per request | 17 statements and about 20 ms per request | 0.1.x | Open |
| I-16 | 3 | Raise the write rate of one tenant: seal audit entries in batches (ADR-0017, option B) | Requests of one tenant queue on its chain | When a tenant needs it | Open |
| I-17 | 3 | Routing constraints by risk class | The link between classification and routing; first deferrable item of ADR-0009 | 0.1.x, after Phase 4 | Done in Phase 4: `router.constraints`, and no model for a system classified as prohibited |
| I-18 | 3 | Post-call policy: detection on completions | Completions are not scanned | 0.1.x | Open |
| I-19 | 3 | Run the outbox dispatcher (`arbiter worker`) | Events are written and nothing consumes them yet | Phase 4 | Done |
| I-20 | 3 | Budgets from the command line; a cache of key lookups with a short lifetime | Budgets need the HTTP API; every request reads the key | 0.1.x | Done: `arbiter budgets create`, `list` and `delete`, audited, with tests. The cache of key lookups was decided against (ADR-0054): keys and roles are read on every request, so that a revocation takes effect at once |
| I-21 | 3 | Measure latency with a real network hop and several processes | The measurement is in process, on one core | 0.3 | Open |
| I-22 | 4 | Have the AI Act rule pack reviewed by a person with legal training | The rules summarise provisions; nobody qualified has checked them | Before 1.0 | Open |
| I-23 | 4 | Spot check of the quoted articles on EUR-Lex by the owner, then `review: confirmed` | ADR-0034; until then outputs say the review is pending | Before 0.1.0 | Open: with the owner |
| I-24 | 4 | Cover provider obligations (Chapter III, Sections 2 and 3) and general-purpose models | Only deployer obligations are evaluated | After 0.1 | Open |
| I-25 | 4 | Discovery of systems from traffic; importers for LiteLLM and JSONL | Deferrable items of ADR-0009; undeclared use is the compensating signal of the threat model | 0.1.x | Done in Phase 4b: the importers (`arbiter ingest`) and discovery by project (`arbiter systems discover`, ADR-0042). Still to verify: the LiteLLM importer against a live LiteLLM |
| I-26 | 4 | System and audit reports; digest delivery by e-mail | Deferrable items of ADR-0009 | 0.1.x | Done in Phase 4b: both reports (`arbiter report`) and `arbiter digest run --send` with a file and an SMTP notifier. The SMTP notifier delivers to the mail catcher of the Compose stack in the container check (ADR-0045). STARTTLS, TLS and authentication are covered only by tests that replace the client |
| I-27 | 4 | Simulation scenarios with labelled outcomes, to measure the scan rules and the PII detectors | Rule precision is unmeasured; the examples are seven hand-written systems | 0.1.x | Partly done in Phase 4b: three scenarios state the tier and the findings expected of eight systems, and the test suite runs them (`arbiter demo`, ADR-0043). They are regression checks on a few cases, not a measurement of precision, and they hold no text, so they say nothing about the PII detectors (I-13 stays open) |
| I-28 | 4 | A guided questionnaire (interactive CLI or a form) instead of editing YAML | Answering sixty questions in a file is the main friction | After 0.1 | Open |
| I-29 | 4 | Repeat the legal text check at every rule pack release, by script, with a search for corrigenda | The check of 2026-10-02 was done by hand | Every pack release | Partly done after Phase 4b: `scripts/check_legal_sources.py` retrieves each source and compares its checksum; run on 2026-10-02, the three sources were unchanged. Open: the search for corrigenda and later amending acts is still done by a person |
| I-30 | 4 | Read `pii_categories` for the scanner without sampling 5,000 rows per system | A portable query on a JSON column was not found | 0.1.x | Done after Phase 4b: the scanner and discovery read the distinct combinations of categories through the text of the column, on SQLite and PostgreSQL. No sample, so no category can be missed; verified by the scanner, discovery and scenario tests on both engines |
| I-31 | 4b | Run the LiteLLM importer against the output of a live LiteLLM proxy, as a container, and pin the version it was checked with | The mapping was written from the documented specification, which states no version | 0.1.x | Open |
| I-32 | 4b | Attribute imported records to a system after the import, so that a candidate from an external source closes when its system is declared | Imported records are attributed at import only; the candidate stays until the records leave the 30-day window | 0.1.x | Open |
| I-33 | 4b | Let a declaration name several projects, and let the gateway resolve the system of a key from its project | A project that runs several systems shows as one candidate; the gateway applies a tier only to keys tied to the system | 0.1.x | Open |
| I-34 | 4b | Reports, discovery and digest delivery over HTTP where they are missing (`systems discover`, `digest --send`) | They exist on the command line only | 0.2 | Done after Phase 4b: `GET /api/v1/candidates` (auditor or admin) and `POST /api/v1/digests/deliveries` (admin; 409 when the configuration cannot deliver, 502 when the server refuses). Reports were already served. Verified by tests on both engines |
| I-35 | 4b | More scenarios, with expected outcomes written by someone other than the author of the rules | Three scenarios, written together with the rules they check | 0.1.x | Open |
| I-36 | 4b | PDF output of the reports as an optional extra | ADR-0044 chose printing the HTML; a scheduled job cannot print | When asked for | Open |
| I-37 | 4b | Escape text typed by people in the cells of Markdown tables | A system name with a `|` or a line break broke the inventory table of the digest | 0.1.x | Done after Phase 4b: a `cell` filter in the templates, with a test |
| I-38 | 2 | Make the message of a missing extra true before publication | It told users to `pip install "ai-arbiter[...]"`, which does not exist yet | 0.1.x | Done after Phase 4b: the message gives the way from a clone first, then the `pip` command "once published" |
| I-39 | 4b | Show and match short ids by their last characters everywhere | Budgets showed the first eight characters of an id, which are a timestamp: two budgets created together looked the same and could not be deleted by short id | 0.1.x | Done in Phase 5: found by a test of the MCP grants; one helper for findings, budgets and grants, with a test that creates two budgets together |
| I-40 | 5 | Run the MCP proxy between a real MCP client and a real MCP server | It was tested against a stand-in server written from the specification | Before 0.2.0 | Done in Phase 5 for the official SDK: the client and a server of `mcp` 2.3.0 are joined through the proxy in process, in the test suite (discovery, a call that is allowed, a call that is refused). Not done: a server or a client of another vendor, and anything over a real network |
| I-41 | 5 | Detect and redact personal data in the arguments and results of MCP calls; filter `tools/list` to what the caller may call | ADR-0049 left content inspection as a deferrable item | 0.2.x | Open |
| I-42 | 5 | Grants for resources and prompts, not only for tools | Anything other than listing and calling a tool needs a grant for the whole server | 0.2.x | Open |
| I-43 | 5 | Read the card of a real A2A agent over the network; read cards on a schedule and report a card that changed | The reader was tested with cards signed in the test suite; cards are read only on request | Before 0.2.0 | Open |
| I-44 | 5 | Follow the key set a card names (`jku`) for domains on an allowlist | ADR-0053 chose configured keys only; keys are rotated by hand | 0.2.x | Open |
| I-45 | 5 | Join the client and a server of the official A2A SDK through the proxy, as was done for MCP | The A2A proxy was tested against a stand-in agent written from the specification | Before 0.2.0 | Open |
| I-46 | 5 | Serve a card at the proxy for each agent, with the proxy's own address in it | Clients are configured with the address of the proxy by hand | 0.2.x | Open |
| I-47 | 5 | Detect health data and the other special categories; measure on a larger set written by someone else, and on real prompt lengths | Neither detector looks for them; the set has about fifty short sentences per language | 0.2.x | Open |

## Licence

Apache-2.0. See [LICENSE](LICENSE).
