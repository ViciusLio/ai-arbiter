# Arbiter

**AI governance gateway and EU AI Act compliance toolkit.**

Arbiter links what AI systems an organisation *says* it runs, as an inventory classified
under the EU AI Act, with what its traffic *shows* it runs. A gateway produces the
evidence and enforces constraints derived from the classification; a compliance toolkit
turns the evidence into classified systems, findings and a daily digest. Either half works
without the other.

> **Status: alpha, not released yet.** The gateway works end to end: an OpenAI-compatible
> endpoint with policy, redaction of personal data, routing, metering, budgets and a
> hash-chained audit log. The compliance toolkit (inventory, AI Act classifier, findings,
> digest) is the next phase. See the [roadmap](#roadmap).

> Arbiter is a support tool. It does not provide legal advice.

This project is published on PyPI as **`ai-arbiter`**. It is not related to `arbiter-ai`
or `arbiter`, which are different projects by other authors.

## Install

```bash
pip install ai-arbiter
```

Or run it without installing:

```bash
uvx ai-arbiter --version
```

The base install is the offline toolkit and CLI, on SQLite. The HTTP gateway is an extra:

```bash
pip install "ai-arbiter[gateway]"
```

## Try it

No Docker and no cloud account needed. The mock provider answers in place of a real
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
arbiter audit verify        # recomputes the hash chain of the audit log
arbiter pii detectors       # what is detected in prompts, and what is not
```

The response header `X-Arbiter-Redacted: email` says the address was replaced before the
prompt left the gateway. Nothing of the prompt is stored.

Any client that speaks the OpenAI API works: point its base URL at
`http://127.0.0.1:8080/v1` and use the Arbiter key as the API key.

The command is `arbiter`; `ai-arbiter` is an alias for it.

## What the gateway does

| Capability | In short |
|---|---|
| Identity | Teams, projects, principals, API keys stored as keyed hashes, three roles |
| Policy | Rules as data: model allowlist, hard budgets, redaction. A denial explains itself |
| Redaction | Personal data and credentials in prompts are masked before the provider sees them |
| Routing | Deployments ordered by priority or cost, with retry and fallback |
| FinOps | Tokens and estimated cost per tenant, team, project, principal and AI system; soft and hard budgets |
| Audit | One hash chain per tenant, verifiable and exportable; no content, no names |
| Providers | OpenAI-compatible endpoints, Azure OpenAI, and a mock |

How to configure and use each of them: [the gateway](docs/gateway.md) and
[the audit log](docs/audit.md).

### Limits you should know

- **Detection of personal data is by format, not by meaning.** The built-in detectors
  find e-mail addresses, phone numbers (international and Italian), IBANs, payment cards,
  Italian fiscal codes and VAT numbers, IP addresses and common credential formats. They
  do **not** find names, postal addresses, dates of birth, health data or anything
  written as free text. Their precision and recall have not been measured yet.
- **Costs are estimates**, computed from a price catalogue you fill in. Arbiter ships no
  prices for real providers.
- **The audit log is tamper-evident, not tamper-proof.** Someone who can write to the
  database can rewrite the whole chain; keep a copy of the head elsewhere.
- **The provider adapters for OpenAI-compatible endpoints and Azure OpenAI have been
  tested against a simulated transport only**, not against a real provider.

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
starts the Compose stack and sends a request through it.

Tests run on SQLite by default. To run them on PostgreSQL as well, set
`ARBITER_TEST_DATABASE_URL` to an empty database; the dev container does this for you.

A container image and a Compose file are in `deploy/`.

## Roadmap

| Version | Content |
|---|---|
| 0.1 | Gateway MVP (OpenAI-compatible proxy, FinOps metering, policy, audit log): **built, not released**. Compliance MVP (inventory, AI Act classifier, findings, daily digest, CLI): next |
| 0.2 | A2A and MCP: agent registry, governed MCP catalogue and proxy, multi-agent demo |
| 0.3 | Azure: Bicep, Container Apps, Entra ID, observability, hardening |
| 1.0 | Documentation, quickstart, demo scenarios |

Design and decisions are in [`docs/architecture`](docs/architecture/README.md) and
[`docs/adr`](docs/adr/README.md).

## Release improvement tracking

At the end of each phase the project records where it stands, strengths and weaknesses
alike, and what would improve it. Rows stay in the table after they are closed.

### Where each phase stands

| Phase | Strengths | Weaknesses |
|---|---|---|
| 0: Analysis | The scope is one end-to-end slice with a core and deferrable parts, decided before any code. The positioning is clear: link the inventory classified under the AI Act with real traffic | AI Act dates come from secondary sources. The analysis is in Italian, the rest of the documentation in English |
| 1: Architecture | 26 decision records with option tables. Module boundaries, data model, interfaces and a first threat model are written down | No prototype was built, so the interfaces are untested. Default PII detection has low recall on names and free text. The audit chain is tamper-evident, not tamper-proof |
| 2: Scaffolding | Every check passes on Python 3.12, 3.13 and 3.14, on SQLite and PostgreSQL, with 98% coverage. The image and the Compose stack run. CI is green on Linux and Windows | The release workflow has never run and `0.0.1` is not published. No product feature exists yet. Telemetry is limited to a tracer bootstrap |
| 3: Gateway | A request goes end to end: key, policy, redaction, routing, metering, audit. Every outcome is an explained decision in a verifiable chain. No prompt text is stored, and a test searches the whole database to prove it. The same tests run on SQLite and PostgreSQL. Decisions were taken before the code and recorded (ADR-0027 to ADR-0031) | The adapters for real providers were never run against one. PII detection misses names and free text, and its precision and recall are not measured. About 20 ms and 17 database statements are added to each request, and the requests of one tenant queue on its audit chain. Nothing is instrumented yet. Deferrable items of ADR-0009 are not started |

### Improvements

| ID | Phase | Improvement | Why | Target | Status |
|---|---|---|---|---|---|
| I-01 | 0 | Verify AI Act dates and the amending regulation on EUR-Lex, article by article | The rule pack must rest on the official text | Before Phase 4 | Open |
| I-02 | 0 | Add an English summary of the Phase 0 analysis | One language across the documentation | 1.0 | Open |
| I-03 | 1 | Revise `interfaces.md` and `data-model.md` against the code at the end of Phase 3 | The design was never prototyped and will drift | End of Phase 3 | Done: both documents list where the code differs |
| I-04 | 1 | Publish precision and recall of each PII detector; offer Presidio as a plugin | Users must see what the default detection misses | 0.1.x | Open |
| I-05 | 1 | Anchor the audit chain head outside the database, then sign checkpoints | A full rewrite of the chain is otherwise undetectable | 0.1.x, then 0.3 | Open |
| I-06 | 2 | Publish `0.0.1` and exercise the release workflow | Reserves the name on PyPI; the workflow is unverified | Before 0.1.0-alpha | Open |
| I-07 | 2 | Set the PostgreSQL test URL in the CI job that tests the base install | That job missed a defect the dev container found | Phase 3 | Done |
| I-08 | 2 | Review the CodeQL alert list | The workflow passes, the alerts were never read | Phase 3 | Open |
| I-09 | 2 | Give each CI job its own uv cache key; pin the runner image | Jobs race to save one cache; `ubuntu-latest` changes on 19 October 2026 | Phase 3 | Done: `ubuntu-24.04`, one cache per job |
| I-10 | 2 | Add metrics, log export and request-path instrumentation | Only tracing is bootstrapped | 0.1.x, then 0.3 | Open: not done in Phase 3 |
| I-11 | 2 | Reduce the image size (316 MB) | Faster pulls and cold starts | 0.3 | Open |
| I-12 | 3 | Run the OpenAI-compatible and Azure OpenAI adapters against real endpoints | They were tested against a simulated transport only | Before 0.1.0 | Open: needs provider credentials from the owner |
| I-13 | 3 | Measure precision and recall of the PII detectors on a labelled set | Redaction is on by default and its error rates are unknown | 0.1.x, with the simulation scenarios | Open |
| I-14 | 3 | Add the deferred detectors: identity documents, phone and VAT formats of other member states | Coverage promised by ADR-0014, deferred by ADR-0027 | 0.1.x | Open |
| I-15 | 3 | Reduce the statements on the request path: one statement for the roll-ups, one audit entry per request | 17 statements and about 20 ms per request | 0.1.x | Open |
| I-16 | 3 | Raise the write rate of one tenant: seal audit entries in batches (ADR-0017, option B) | Requests of one tenant queue on its chain | When a tenant needs it | Open |
| I-17 | 3 | Routing constraints by risk class | The link between classification and routing; first deferrable item of ADR-0009 | 0.1.x, after Phase 4 | Open |
| I-18 | 3 | Post-call policy: detection on completions | Completions are not scanned | 0.1.x | Open |
| I-19 | 3 | Run the outbox dispatcher (`arbiter worker`) | Events are written and nothing consumes them yet | Phase 4 | Open |
| I-20 | 3 | Budgets from the command line; a cache of key lookups with a short lifetime | Budgets need the HTTP API; every request reads the key | 0.1.x | Open |
| I-21 | 3 | Measure latency with a real network hop and several processes | The measurement is in process, on one core | 0.3 | Open |

## Licence

Apache-2.0. See [LICENSE](LICENSE).
