# Arbiter

**AI governance gateway and EU AI Act compliance toolkit.**

Arbiter links what AI systems an organisation *says* it runs, as an inventory classified
under the EU AI Act, with what its traffic *shows* it runs. A gateway produces the
evidence and enforces constraints derived from the classification; a compliance toolkit
turns the evidence into classified systems, findings and a daily digest. Either half works
without the other.

> **Status: pre-alpha.** This release contains the project foundation only: configuration,
> persistence, the event outbox, the plugin registry and the command-line skeleton. The
> gateway and the compliance toolkit are under development. See the
> [roadmap](#roadmap).

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

No Docker and no cloud account needed.

```bash
arbiter init            # writes arbiter.yaml and creates a local SQLite database
arbiter config show     # effective configuration, credentials masked
arbiter plugins list    # installed plugins and which ones are active
arbiter db current      # schema revision of the database
arbiter serve           # HTTP application with /healthz and /readyz (gateway extra)
```

The command is `arbiter`; `ai-arbiter` is an alias for it.

## Configuration

One settings tree, validated at startup. Precedence, highest first:

1. environment variables: prefix `ARBITER_`, nested keys joined by `__`
   (for example `ARBITER_DATABASE__URL`);
2. `arbiter.yaml`, or the file named by `--config` or `ARBITER_CONFIG`;
3. built-in defaults.

Secrets are never written in configuration. They are referenced as `secret://NAME` and
resolved by the active secret store; the default one reads `ARBITER_SECRET_NAME`.

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

`scripts/check.sh` runs all of the above on every supported Python version;
`scripts/check.sh --containers` also builds the image and starts the Compose stack.

Tests run on SQLite by default. To run them on PostgreSQL as well, set
`ARBITER_TEST_DATABASE_URL` to an empty database; the dev container does this for you.

A container image and a Compose file are in `deploy/`.

## Roadmap

| Version | Content |
|---|---|
| 0.1 | Gateway MVP (OpenAI-compatible proxy, FinOps metering, policy, audit log) and compliance MVP (inventory, AI Act classifier, findings, daily digest, CLI) |
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
| 0 — Analysis | The scope is one end-to-end slice with a core and deferrable parts, decided before any code. The positioning is clear: link the inventory classified under the AI Act with real traffic | AI Act dates come from secondary sources. The analysis is in Italian, the rest of the documentation in English |
| 1 — Architecture | 26 decision records with option tables. Module boundaries, data model, interfaces and a first threat model are written down | No prototype was built, so the interfaces are untested. Default PII detection has low recall on names and free text. The audit chain is tamper-evident, not tamper-proof |
| 2 — Scaffolding | Every check passes on Python 3.12, 3.13 and 3.14, on SQLite and PostgreSQL, with 98% coverage. The image and the Compose stack run. CI is green on Linux and Windows | The release workflow has never run and `0.0.1` is not published. No product feature exists yet. Telemetry is limited to a tracer bootstrap |

### Improvements

| ID | Phase | Improvement | Why | Target | Status |
|---|---|---|---|---|---|
| I-01 | 0 | Verify AI Act dates and the amending regulation on EUR-Lex, article by article | The rule pack must rest on the official text | Before Phase 4 | Open |
| I-02 | 0 | Add an English summary of the Phase 0 analysis | One language across the documentation | 1.0 | Open |
| I-03 | 1 | Revise `interfaces.md` and `data-model.md` against the code at the end of Phase 3 | The design was never prototyped and will drift | End of Phase 3 | Open |
| I-04 | 1 | Publish precision and recall of each PII detector; offer Presidio as a plugin | Users must see what the default detection misses | 0.1.x | Open |
| I-05 | 1 | Anchor the audit chain head outside the database, then sign checkpoints | A full rewrite of the chain is otherwise undetectable | 0.1.x, then 0.3 | Open |
| I-06 | 2 | Publish `0.0.1` and exercise the release workflow | Reserves the name on PyPI; the workflow is unverified | Before 0.1.0-alpha | Open |
| I-07 | 2 | Set the PostgreSQL test URL in the CI job that tests the base install | That job missed a defect the dev container found | Phase 3 | Open |
| I-08 | 2 | Review the CodeQL alert list | The workflow passes, the alerts were never read | Phase 3 | Open |
| I-09 | 2 | Give each CI job its own uv cache key; pin the runner image | Jobs race to save one cache; `ubuntu-latest` changes on 19 October 2026 | Phase 3 | Open |
| I-10 | 2 | Add metrics, log export and request-path instrumentation | Only tracing is bootstrapped | Phase 3, then 0.3 | Open |
| I-11 | 2 | Reduce the image size (316 MB) | Faster pulls and cold starts | 0.3 | Open |

## Licence

Apache-2.0. See [LICENSE](LICENSE).
