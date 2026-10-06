# Getting started

Install Arbiter, make a first request through the gateway, declare a few systems and
see what the toolkit makes of them. Everything here runs on one machine, with a mock in
place of a real model.

> Arbiter is a support tool. It does not provide legal advice.

## Install

Needs Python 3.12 or newer. The releases so far are pre-releases, which `pip` skips
unless the requirement names one:

```bash
pip install "ai-arbiter>=0.1.0a1"                 # the toolkit and the command line, on SQLite
pip install "ai-arbiter[gateway,mcp]>=0.1.0a1"    # with the HTTP gateway and the MCP proxy
```

Do not use `pip install --pre`. That flag takes pre-releases of every dependency too,
not only of Arbiter, and a pre-release of one of them is a different library that breaks
the proxies.

Or run it without installing:

```bash
uvx --from "ai-arbiter>=0.1.0a1" arbiter --version
```

From a clone: `uv sync --all-extras`, then `uv run arbiter`.

The base install is the offline toolkit and CLI, on SQLite. The HTTP gateway, the
proxies, the detection of names, PDF and tracing are extras: `gateway`, `mcp`, `a2a`,
`pii`, `pdf`, `otel`, or `all`.

## First steps

From a clone, put `uv run` in front of each command below. No Docker and no cloud
account needed. The mock
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
arbiter demo tour --case consulting --report out/demo.html   # a firm that approved one family of models; the run as a page
arbiter demo run --all                           # three invented scenarios, in the tenant "demo"
```

Any client that speaks the OpenAI API works: point its base URL at
`http://127.0.0.1:8080/v1` and use the Arbiter key as the API key.

The command is `arbiter`; `ai-arbiter` is an alias for it.

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
catcher of the stack and runs the scenarios and the guided demonstration in the
container.

Tests run on SQLite by default. To run them on PostgreSQL as well, set
`ARBITER_TEST_DATABASE_URL` to an empty database; the dev container does this for you.

A container image and a Compose file are in `deploy/`.


## Where to go next

- [Giving a demonstration](demo.md): the guided tour, the use case told as a story, a
  live session.
- [The gateway](gateway.md) and [the audit log](audit.md).
- [The compliance toolkit](compliance.md).
- [Scope and limits](scope-and-limits.md).
