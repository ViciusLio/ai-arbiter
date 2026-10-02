# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries link to the decision record that motivated them, where one exists.

## [Unreleased]

### Added

- **Gateway** (Phase 3). An OpenAI-compatible endpoint, `POST /v1/chat/completions` with
  streaming and `GET /v1/models`, that authenticates, applies policy, routes, meters and
  audits every request. Prompt and completion text is not stored
  ([ADR-0018](docs/adr/0018-metadata-only-by-default.md)). Guide: `docs/gateway.md`.
- Identity: teams, projects, principals, three roles (admin, auditor, developer) scoped
  to a tenant, a team or a project, and API keys with a recognisable format, stored as an
  HMAC keyed with a pepper that can be rotated
  ([ADR-0028](docs/adr/0028-api-keys-hmac-with-pepper.md)).
- Rule engine: rule packs as validated YAML with a closed set of operators, evaluated
  with a trace of the conditions behind each match; the decision envelope shared by every
  automated outcome ([ADR-0012](docs/adr/0012-unified-declarative-rule-engine.md)).
- Audit log: one hash chain per tenant over RFC 8785 canonical JSON, with verification
  that reports the first broken link and a JSONL export that can be verified without the
  database; `audit.fail_mode`, per tenant
  ([ADR-0017](docs/adr/0017-audit-hash-chain-per-tenant.md),
  [ADR-0029](docs/adr/0029-canonical-json-in-house.md)). Guide: `docs/audit.md`.
- Model providers as plugins: a scriptable mock, OpenAI-compatible endpoints and Azure
  OpenAI, each validating the settings of its deployments at startup
  ([ADR-0013](docs/adr/0013-own-llm-provider-adapters.md)). The two HTTP adapters are
  tested against a simulated transport, not against a real provider.
- Routing by priority or by cost, with retry and fallback; the plan and every attempt
  are an audited decision.
- FinOps: a versioned price catalogue with overrides, costs as exact decimals, usage
  roll-ups per tenant, team, project, principal and AI system, soft and hard budgets, a
  usage API and a Markdown usage report in English and Italian
  ([ADR-0030](docs/adr/0030-price-catalogue-as-versioned-file.md)). Interactions without
  token counts are reported as unpriced; a deployment can opt in to flagged estimates
  ([ADR-0031](docs/adr/0031-token-counts-unknown-by-default.md)).
- Detection and redaction of personal data in prompts: e-mail, phone, IBAN, payment
  card, Italian fiscal code and VAT number, IP address and common credential formats,
  replaced by masking, keyed hashing or removal
  ([ADR-0014](docs/adr/0014-pii-detection-built-in-and-pluggable.md),
  [ADR-0027](docs/adr/0027-pii-detectors-core-and-deferrable.md)).
- Pre-call policy with a default rule pack: model allowlist, hard budgets, redaction. A
  denied request returns the decision and the rules that matched, in English or Italian.
- Control plane under `/api/v1`: teams, projects, principals, roles, API keys, budgets,
  usage, audit entries, verification and export. Errors are RFC 9457 problem details.
- CLI: `arbiter keys create|list|revoke`, `arbiter usage report`,
  `arbiter audit verify|export`, `arbiter pii detectors|redact`. `arbiter init` generates
  the secrets of a local workspace in `.env` and a starter configuration with the mock
  provider; `arbiter serve` checks the configuration before starting.
- Message catalogues in English and Italian, with Babel for numbers and dates
  ([ADR-0021](docs/adr/0021-i18n-message-catalogs.md)).
- `scripts/measure_latency.py`: the time the gateway adds to a request, against the mock
  provider; run by `scripts/check.sh` and in CI.
- "Release improvement tracking" in the README: strengths, weaknesses and improvements
  recorded at the end of each phase.
- Package `ai-arbiter` with the import package `ai_arbiter` and the `arbiter` command,
  alias `ai-arbiter` ([ADR-0005](docs/adr/0005-naming-and-distribution.md)). One
  distribution with the optional extras `gateway`, `otel` and `all`; the base install has
  no web framework and no cloud SDK
  ([ADR-0010](docs/adr/0010-single-distribution-with-enforced-boundaries.md)).
- Layered configuration: defaults, `arbiter.yaml`, `ARBITER_*` environment variables and
  explicit overrides, validated at load; `secret://NAME` references resolved through a
  secret store.
- Plugin registry based on entry points; a plugin is loaded only when configuration names
  it ([ADR-0011](docs/adr/0011-plugins-via-entry-points-and-config.md)). Built-in
  plugins: environment secret store, in-process event bus.
- Persistence on SQLite and PostgreSQL with one schema: async engine, UTC timestamp type,
  UUIDv7 keys, `tenant` table, Alembic migrations shipped in the package
  ([ADR-0015](docs/adr/0015-postgres-and-sqlite-row-level-tenancy.md)).
- Event outbox: events are written in the transaction that causes them and delivered at
  least once by a dispatcher
  ([ADR-0016](docs/adr/0016-in-process-events-with-outbox.md)).
- HTTP application with `/healthz` and `/readyz`; readiness requires a reachable database
  at the expected schema revision
  ([ADR-0020](docs/adr/0020-modular-monolith-with-roles.md)).
- CLI commands `init`, `config show`, `plugins list`, `db upgrade`, `db current`, `serve`.
- OpenTelemetry tracer bootstrap behind the `otel` extra.
- Import rules checked by import-linter: the core depends on no other Arbiter package,
  gateway and compliance do not import each other, adapters are wired only at the
  composition roots, the web framework is imported only by `gateway.api`.
- Container image and Compose stack (Arbiter, PostgreSQL, Mailpit), built and smoke-tested
  in CI; the project also runs with no container runtime
  ([ADR-0025](docs/adr/0025-docker-free-local-development.md)).
- GitHub Actions: lint, type-check, tests on Linux and Windows and on PostgreSQL, tests of
  the base install, dependency audit, secret scan, CodeQL, image build; Dependabot
  ([ADR-0024](docs/adr/0024-development-tooling-baseline.md)).
- Dev container for GitHub Codespaces with Python 3.12, 3.13 and 3.14, uv,
  Docker-in-Docker and a PostgreSQL test database; `scripts/check.sh` runs every CI check
  locally ([ADR-0026](docs/adr/0026-codespaces-development-environment.md)).
- Project links and author in the package metadata.
- Release workflow publishing to PyPI through Trusted Publishing, triggered by a version
  tag; procedure in `docs/releasing.md`.
- Apache-2.0 licence, `NOTICE`, `README.md`.
- Project brief with the initial requirements (`docs/PROJECT_BRIEF.md`).
- Phase documents: analysis (Phase 0), architecture (Phase 1), scaffolding (Phase 2), in
  `docs/phases/`.
- Architecture documentation: overview with component and topology diagrams, flows, data
  model, interfaces and a first threat model (`docs/architecture/`).
- Decision records, with an index and the open questions in `docs/adr/README.md`:
  - process ([ADR-0001](docs/adr/0001-use-madr-for-decision-records.md));
  - compliance-first positioning, A2A and MCP on the v0.2 roadmap, ingestion from
    external gateways ([ADR-0002](docs/adr/0002-compliance-first-positioning.md));
  - deterministic classification with rules as versioned data; an LLM may suggest but
    never decide ([ADR-0003](docs/adr/0003-deterministic-classifier-rules-as-data.md));
  - English artifacts, outputs localised in English and Italian
    ([ADR-0004](docs/adr/0004-english-artifacts-localised-outputs.md),
    [ADR-0021](docs/adr/0021-i18n-message-catalogs.md));
  - no web UI in v0.1 ([ADR-0006](docs/adr/0006-no-web-ui-in-v0-1.md));
  - AI Act operator roles, explicit and one-to-many, deployer first
    ([ADR-0007](docs/adr/0007-ai-act-role-explicit-deployer-first.md),
    [ADR-0022](docs/adr/0022-ai-act-roles-one-to-many.md));
  - local-only development until Phase 6
    ([ADR-0008](docs/adr/0008-local-only-until-phase-6.md));
  - v0.1 scope: a core required for `0.1.0` and components that may follow in v0.1.x
    ([ADR-0009](docs/adr/0009-v0-1-scope.md));
  - one declarative rule engine for policy, classification and scanning
    ([ADR-0012](docs/adr/0012-unified-declarative-rule-engine.md));
  - own provider adapters, Azure OpenAI included from v0.1
    ([ADR-0013](docs/adr/0013-own-llm-provider-adapters.md));
  - built-in PII detectors covering EU and Italian formats, pluggable for more
    ([ADR-0014](docs/adr/0014-pii-detection-built-in-and-pluggable.md));
  - per-tenant audit hash chain, fail-closed by default and configurable per tenant, with
    external anchoring of the chain head
    ([ADR-0017](docs/adr/0017-audit-hash-chain-per-tenant.md));
  - audit log placed in the shared core
    ([ADR-0023](docs/adr/0023-audit-log-in-shared-core.md));
  - metadata-only persistence by default
    ([ADR-0018](docs/adr/0018-metadata-only-by-default.md));
  - ingestion of external gateway data through source adapters
    ([ADR-0019](docs/adr/0019-external-telemetry-ingestion.md));
  - the v0.1 split confirmed, with the built-in PII detectors divided between the core
    and v0.1.x ([ADR-0027](docs/adr/0027-pii-detectors-core-and-deferrable.md));
  - API keys with a recognisable format, stored as an HMAC keyed with a pepper
    ([ADR-0028](docs/adr/0028-api-keys-hmac-with-pepper.md));
  - in-house RFC 8785 canonical JSON without floats for the audit hash
    ([ADR-0029](docs/adr/0029-canonical-json-in-house.md));
  - prices in a versioned YAML catalogue, currency converted only when reporting
    ([ADR-0030](docs/adr/0030-price-catalogue-as-versioned-file.md));
  - token counts left unknown when a provider returns no usage, with an opt-in estimate
    ([ADR-0031](docs/adr/0031-token-counts-unknown-by-default.md)).

### Changed

- The em-dash character is no longer used anywhere in the repository; a check in
  `scripts/check.sh` and in CI fails when a tracked file contains one.
- SQLite transactions now start as write transactions, so that concurrent writers queue
  instead of failing with "database is locked".
- The environment secret store also reads `.env` in the working directory; the
  environment wins.
- The Compose stack initialises a local workspace with the mock provider, and its smoke
  test sends a request through the gateway and verifies the audit chain.
- CI: the Linux runner image is pinned, each job has its own dependency cache, the job
  that tests the base install is offered a PostgreSQL database it must not use, and the
  built wheel is checked for its data files.
- New base dependency: Babel. New development dependency: `rfc8785`, used only by the
  tests to check the canonical JSON against an independent implementation.

### Fixed

- A PostgreSQL database URL on an install without the `gateway` extra failed with an
  import error and a traceback. It now reports which extra to install
  ([ADR-0010](docs/adr/0010-single-distribution-with-enforced-boundaries.md)).
- PostgreSQL tests ran, and failed, in an environment without the PostgreSQL driver when
  a test database URL was set, as it is in the dev container. They are now skipped there.
