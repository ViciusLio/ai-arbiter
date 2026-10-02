# Phase 2: Scaffolding

- **Status**: implemented and verified in Codespaces on 2026-10-02:
  `scripts/check.sh --containers` passes to the end (ADR-0026). ADR-0024 and ADR-0025
  accepted on 2026-10-02. The owner gave the go-ahead for Phase 3 the same day. Still
  not run: the release workflow
- **Date**: 2026-10-02
- **Inputs**: Phase 1 decisions (ADR-0010 to ADR-0023), the constraint that Docker is not
  available on the development machine
- **Expected output from the project owner**: decisions on ADR-0024, ADR-0025 and the
  open questions in the [ADR index](../adr/README.md)

## Tasks

| Task | Result |
|---|---|
| Record the Phase 1 decisions | ADR-0010 to ADR-0021 accepted, four of them amended as decided; ADR-0022 (roles one-to-many) and ADR-0023 (audit in core) added |
| Project metadata and tooling | `pyproject.toml`: one distribution with `gateway`, `otel` and `all` extras; ruff, mypy strict, pytest with an 80% coverage gate, import-linter contracts; `uv.lock` |
| Repository files | Apache-2.0 `LICENSE`, `NOTICE`, `.gitignore`, `.gitattributes`, `.editorconfig`, `.env.example`, `README.md` |
| Core: configuration | Layered settings (defaults → YAML file → environment → explicit overrides), validated at load, unknown keys rejected, credentials masked when printed; `secret://` references |
| Core: domain | UUIDv7 identifiers, UTC clock, tenant context |
| Core: plugins | Entry-point registry; plugins are loaded only when named |
| Core: persistence | Async engine and sessions, portable UTC timestamp type, `tenant` table, programmatic Alembic migrations shipped in the package |
| Core: events | Event envelope, `outbox_event` table, in-process bus with transactional publish, at-least-once dispatch with retry limit |
| Core: telemetry | Logging setup; OpenTelemetry tracer bootstrap behind the `otel` extra |
| Adapters | Environment-variable secret store |
| Gateway | Application factory with `/healthz` and `/readyz`; OpenAPI metadata with the disclaimer |
| CLI | `arbiter` (alias `ai-arbiter`): `--version`, `init`, `config show`, `plugins list`, `db upgrade`, `db current`, `serve` |
| Containers | `deploy/docker/Dockerfile` (multi-stage, non-root), `deploy/compose/compose.yaml` (Arbiter, PostgreSQL, Mailpit) |
| CI | `ci.yml` (lint, tests on Linux and Windows, PostgreSQL, base install, dependency audit, secret scan, image and Compose smoke test), `codeql.yml`, `dependabot.yml` |
| Release | `release.yml` with PyPI Trusted Publishing, triggered by a version tag; steps in [releasing.md](../releasing.md) |

## What was verified, and how

Run on the development machine (Windows 11):

| Check | Result |
|---|---|
| Test suite on Python 3.13 | 93 passed, 23 skipped |
| Test suite on Python 3.14 | 93 passed, 23 skipped |
| Test suite without extras (base install) | 85 passed, 23 skipped |
| Coverage, whole package | 98% (gate: 80%) |
| `ruff check`, `ruff format --check` | Clean |
| `mypy` strict, sources and tests | Clean |
| `lint-imports` | 4 contracts kept; each was also shown to fail when deliberately violated |
| Wheel built and installed without extras in a clean environment | `arbiter --version`, `init`, `db current`, `plugins list` work; `serve` refuses with the instruction to install the extra |
| HTTP application started for real | `/healthz` and `/readyz` return 200; OpenAPI document served |
| Workflow and Compose files | Parse as YAML |

In the full runs, the 23 skipped tests are the PostgreSQL variants of the database tests:
every database test is written once and runs on both engines, and the PostgreSQL run
needs `ARBITER_TEST_DATABASE_URL`. In the run without extras, the skips are the
PostgreSQL variants plus the tests that need the web stack or OpenTelemetry.

**Not verified when the phase was written.** These existed but had never run:

| Item | Why | First real run | Outcome |
|---|---|---|---|
| Anything on Python 3.12 | Not installed locally; 3.13 and 3.14 were used | CI | Passed |
| Anything on PostgreSQL | No PostgreSQL and no Docker locally | CI job `test-postgres` | Passed |
| Dockerfile, Compose file | No Docker locally (ADR-0025) | CI job `container` | Passed |
| The GitHub Actions workflows themselves | The repository was not on GitHub yet | First push | All jobs passed |
| `pip-audit` | Blocked locally by TLS interception on the corporate network | CI job `security` | Passed |
| gitleaks | Needs Docker | CI job `security` | Passed |
| Release workflow and Trusted Publishing | Needs the repository and the PyPI publisher | The `0.0.1` release | Not run yet |

The outcomes are those of the first CI run, on 2026-10-02 at commit `87199f1`. Every job
passed; the warning that the first run would need fixes was wrong. Only step outcomes and
annotations were read, not the job logs. Two annotations, neither blocking: jobs race to
save the same uv cache, and `ubuntu-latest` moves to Ubuntu 26 from 19 October 2026.

Added after the phase: the dev container (`.devcontainer/`) and `scripts/check.sh`,
written on a machine that cannot run them. First run in Codespaces, 2026-10-02:

| Item | Outcome |
|---|---|
| Dev container | Builds and starts |
| `scripts/check.sh` | Failed at the step "Tests without extras"; see below |

The failure was a defect, not an environment problem. The dev container sets
`ARBITER_TEST_DATABASE_URL`, so the PostgreSQL variants of the database tests ran in the
environment without extras, which has no PostgreSQL driver. CI did not catch it because
its base-install job does not set that variable. Two fixes:

- the test fixture skips the PostgreSQL variants when the driver is not installed;
- a PostgreSQL URL on an install without the `gateway` extra now raises
  `MissingExtraError` naming the extra, and the CLI prints it as an error instead of a
  traceback. This was a real gap for users, independent of the tests.

### Full run in Codespaces

`scripts/check.sh --containers` run to the end in the dev container on 2026-10-02, at
commit `c8ccce3`, with exit status 0 and no change needed:

| Check | Result |
|---|---|
| Tools in the dev container | uv 0.12.22; Python 3.12.15, 3.13.16, 3.14.8 installed by uv; Docker 29.8.2 client and server; the `postgres` sidecar accepts connections; `ARBITER_TEST_DATABASE_URL` is set |
| Lock file, install with all extras | Up to date; installs on Python 3.12 |
| `ruff check`, `ruff format --check` | Clean |
| `mypy` strict | No issues in 53 source files |
| `lint-imports` | 4 contracts kept |
| Test suite on Python 3.12, with coverage | 121 passed, none skipped; coverage 98% (gate: 80%) |
| Test suite on Python 3.13 | 121 passed |
| Test suite on Python 3.14 | 121 passed |
| Database tests on PostgreSQL | The 23 database tests passed on SQLite and on PostgreSQL in the same run |
| Test suite without extras | 90 passed, 23 skipped: 19 PostgreSQL variants, 4 that need the web stack or OpenTelemetry |
| Image build | `ai-arbiter:dev` built, 316 MB |
| Image user | Runs as uid 10001 |
| Compose stack | Arbiter and PostgreSQL reach the healthy state; Mailpit starts |
| Health endpoints of the stack | `/healthz` returns `ok` with version `0.0.1`; `/readyz` returns `ready` with the database check `ok` |
| CI at commit `c8ccce3` | Every job passed, CodeQL included |

Not verified in this run:

| Item | Why |
|---|---|
| Release workflow and Trusted Publishing | Runs on a version tag pushed by the owner. Nothing has been published: the `0.0.1` planned here was later replaced by `0.1.0a1` (ADR-0032) |
| CodeQL alerts | The workflow passed, but the alert list is not readable with the Codespaces token; the owner checks the Security tab |
| Mailpit beyond starting | Nothing sends mail before Phase 4 |
| Dev container outside Codespaces | Only Codespaces was used |

Two harmless warnings appear in the run: uv cannot inspect the system `python3` of the
dev container image, which the project does not use, and uv notes that `VIRTUAL_ENV`
differs from the per-version environments the script selects.

## Decisions made in this phase

| ADR | Decision | Status |
|---|---|---|
| [0022](../adr/0022-ai-act-roles-one-to-many.md) | AI Act roles as a one-to-many relation | Accepted |
| [0023](../adr/0023-audit-log-in-shared-core.md) | Audit log in the shared core | Accepted |
| [0024](../adr/0024-development-tooling-baseline.md) | Tooling baseline: hatchling, Typer, pytest-asyncio, import-linter, pip-audit, gitleaks, CodeQL, SHA-pinned actions | Accepted |
| [0025](../adr/0025-docker-free-local-development.md) | Local development without Docker; containers built and tested in CI | Accepted, extended by 0026 |
| [0026](../adr/0026-codespaces-development-environment.md) | Development in GitHub Codespaces with a dev container | Accepted |

ADR-0024 and ADR-0025 were applied before acceptance and accepted afterwards.

## Things that turned out differently from the design

- **Ports.** `core.ports` holds only the three ports that have an implementation today
  (`Clock`, `SecretStore`, `EventBus`). The others listed in
  [interfaces.md](../architecture/interfaces.md) are added with the module that needs
  them, so that no interface exists without a user.
- **Plugin settings.** ADR-0011 says each plugin declares its own settings model. The two
  plugins that exist need no settings, so that mechanism arrives in Phase 3 with the
  first configurable plugin (a model provider).
- **Telemetry.** Only tracing is bootstrapped, and the provider is returned to the caller
  instead of being installed globally. Metrics, log export and instrumentation of the
  request path come with the gateway (Phase 3) and Azure Monitor (Phase 6).
- **Compose.** The stack has no separate migration service; the application container
  migrates and then serves. A mock model provider needs no container because it is an
  in-process adapter (ADR-0013). Azure emulators are added when the adapters they stand in
  for exist.
- **Package author.** Set to "ViciusLio" in `pyproject.toml` and `NOTICE`, as decided by
  the project owner.

## Defects found by the tests while building

- The readiness check caught only `SQLAlchemyError`; an unreachable PostgreSQL raises a
  plain `OSError` from the driver, which turned a 503 into a crash. Fixed.
- Alembic logged at INFO on every readiness probe. Silenced to WARNING.

## Open questions

See the [ADR index](../adr/README.md). The ones that matter next:

1. Azure subscription and budget (ADR-0008): the owner decides by Phase 6.
2. Everything under "Not verified" was checked in Codespaces on 2026-10-02, except the
   release workflow and the CodeQL alert list.

The v0.1 scope (ADR-0009) was accepted after this phase, split into a core and components
that may follow in v0.1.x.

## Proposed Phase 3 task list

Gateway MVP: `llm_router`, `finops`, `audit`, basic `policy`.

1. Identity: teams, projects, principals, API keys, three roles.
2. Rule engine (`core.rules`): rule pack schema, condition evaluator, match trace.
3. Redaction: built-in detectors with EU and Italian formats (ADR-0014).
4. Audit: hash chain, verification, export, external anchoring (ADR-0017).
5. Policy: fact collection, pre- and post-call evaluation, default policy pack.
6. Providers: mock, OpenAI-compatible, Azure OpenAI; plugin settings models.
7. Router: candidates, constraints, priority and cost strategies, fallback and retry.
8. FinOps: versioned price catalogue, metering, roll-ups, budgets.
9. HTTP: `/v1/chat/completions` with streaming, `/v1/models`, admin endpoints.
10. Request-path latency measured against the mock provider.

Decisions to bring to you in Phase 3, each with its option table: API key format and
hashing; canonical JSON implementation for the audit hash; price catalogue format and
currency handling; token counting when a provider returns no usage.

---

*Arbiter is a support tool and does not provide legal advice.*
