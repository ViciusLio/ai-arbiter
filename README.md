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

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
```

Tests run on SQLite by default. To run them on PostgreSQL as well, set
`ARBITER_TEST_DATABASE_URL` to an empty database.

A container image and a Compose file are in `deploy/`; they are built and tested in CI.

## Roadmap

| Version | Content |
|---|---|
| 0.1 | Gateway MVP (OpenAI-compatible proxy, FinOps metering, policy, audit log) and compliance MVP (inventory, AI Act classifier, findings, daily digest, CLI) |
| 0.2 | A2A and MCP: agent registry, governed MCP catalogue and proxy, multi-agent demo |
| 0.3 | Azure: Bicep, Container Apps, Entra ID, observability, hardening |
| 1.0 | Documentation, quickstart, demo scenarios |

Design and decisions are in [`docs/architecture`](docs/architecture/README.md) and
[`docs/adr`](docs/adr/README.md).

## Licence

Apache-2.0. See [LICENSE](LICENSE).
