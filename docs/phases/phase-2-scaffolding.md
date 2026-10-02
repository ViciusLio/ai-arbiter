# Phase 2 — Scaffolding

- **Status**: implemented; ADR-0024 and ADR-0025 accepted on 2026-10-02. Approval of the
  phase waits for the verification in Codespaces of the items listed under "Not verified"
  (ADR-0026)
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

**Not verified.** These exist but have never run:

| Item | Why | First real run |
|---|---|---|
| Anything on Python 3.12 | Not installed locally; 3.13 and 3.14 were used | CI |
| Anything on PostgreSQL | No PostgreSQL and no Docker locally | CI job `test-postgres` |
| Dockerfile, Compose file | No Docker locally (ADR-0025) | CI job `container` |
| The GitHub Actions workflows themselves | The repository is not on GitHub yet | First push |
| `pip-audit` | Blocked locally by TLS interception on the corporate network | CI job `security` |
| gitleaks | Needs Docker | CI job `security` |
| Release workflow and Trusted Publishing | Needs the repository and the PyPI publisher | The `0.0.1` release |

Expect the first CI run to need fixes. The workflows use action versions newer than any
that were tested here.

Added after the phase, and equally unverified: the dev container (`.devcontainer/`) and
`scripts/check.sh`. They were written on a machine that cannot run them. The first
codespace is their first run; the checklist is in `CLAUDE.md`, section "Resume here".

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

1. ADR-0009 (v0.1 scope) is still unconfirmed.
2. Azure subscription and budget (ADR-0008): the owner decides by Phase 6.
3. Everything under "Not verified" has to be checked in Codespaces before Phase 3.

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
