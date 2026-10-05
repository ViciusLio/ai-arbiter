# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries link to the decision record that motivated them, where one exists.

## [Unreleased]

### Added

- **Deferrable items of v0.1** (Phase 4b,
  [ADR-0040](docs/adr/0040-deferrable-items-before-0-1-0.md)).
  - Importers for the records of another gateway: Arbiter's canonical JSON lines and
    the LiteLLM standard logging payload, with `arbiter ingest`. Content is dropped on
    the way in, a repeated import adds nothing, and records are attributed to declared
    systems by a tag or by configured mappings
    ([ADR-0019](docs/adr/0019-external-telemetry-ingestion.md)). The LiteLLM mapping follows its
    documented specification and was not run against a live LiteLLM.
  - System report and audit report, in Markdown and HTML, in English and Italian:
    `arbiter report system KEY`, `arbiter report audit`, and
    `GET /api/v1/systems/{key}/report`, `GET /api/v1/audit/report`.
  - Discovery of systems from traffic
    ([ADR-0042](docs/adr/0042-discovered-systems-by-project.md)): requests that belong to
    no declared system are grouped by project, or by the group an imported source names,
    and the scan reports one finding per candidate (scan pack `2026.10.1`, rule
    `SCAN-UNDECLARED-SYSTEM-CANDIDATE`). `arbiter systems discover` lists them and
    `--draft` prints declarations for a person to complete. A declared system that names
    its project counts that project's unattributed requests as its own.
  - Simulation scenarios
    ([ADR-0043](docs/adr/0043-simulation-scenarios-as-data.md)): three YAML scenarios of
    invented systems and traffic, each with the tier and the findings it expects.
    `arbiter demo list` and `arbiter demo run NAME` load them into the tenant `demo` and
    compare the outcome; the test suite runs them all.
  - The HTML reports and the HTML digest carry a print style sheet; there is no PDF
    output ([ADR-0044](docs/adr/0044-reports-without-pdf.md)).
  - The container check sends the digest to the mail catcher of the Compose stack
    ([ADR-0045](docs/adr/0045-smtp-checked-against-the-compose-mail-catcher.md)).
  - Digest delivery: `arbiter digest run --send` sends the digest to the configured
    recipients, each in their language, through the `Notifier` port. Two notifiers:
    `file`, the default, which writes `.eml` files and sends nothing, and `smtp`, which
    uses the standard library and takes its password from a secret reference. Each
    delivery is an audit entry without addresses. The `smtp` notifier was not run
    against a real mail server.
- **A2A and MCP** (Phase 5;
  [ADR-0046](docs/adr/0046-mcp-proxy-speaks-the-modern-revision.md) to
  [ADR-0054](docs/adr/0054-no-cache-of-key-lookups.md)).
  - MCP catalogue: servers, the names of the tools they list, and grants to the
    tenant, a project or an AI system, for one tool or for all. Nothing is allowed
    without a grant. `arbiter mcp servers`, `arbiter mcp grants`, `/api/v1/mcp`.
  - MCP proxy: `POST /mcp/{server}` is the MCP endpoint of a server of the catalogue,
    for revision `2026-07-28` over Streamable HTTP. A call is checked against its
    headers as the revision requires, decided by a rule pack (`rulepacks/mcp`), written
    to the audit log and to the new table `invocation` before it is forwarded, and
    forwarded with the credential of the catalogue. Arguments and results are never
    stored. A new server role, `mcp`, and a new optional extra, `mcp`.
  - `arbiter mcp servers refresh` and `POST /api/v1/mcp/servers/{key}/discovery` ask a
    server which revisions it speaks and which tools it lists.
  - The test suite joins the client and a server of the official MCP SDK through the
    proxy, in process. The SDK is a development dependency only.
  - A2A Agent Cards are read and their signatures judged against keys the operator
    trusts, through the official A2A SDK behind a port; a key a card names for itself is
    never fetched
    ([ADR-0053](docs/adr/0053-a2a-card-signatures-against-configured-keys.md)). New
    optional extra, `a2a`.
  - A2A registry: agents registered by the address of their card, read over https
    without following redirects; the name, the version, the interfaces and a checksum of
    the card are kept. An interface counts only on the host the card was read from.
    Grants to the tenant, a project or an AI system. `arbiter a2a agents`,
    `arbiter a2a grants`, `/api/v1/a2a`
    ([ADR-0051](docs/adr/0051-a2a-registry-then-proxy.md)).
  - A2A proxy: `POST /a2a/{agent}` for the JSON-RPC binding and `/a2a/{agent}/rest/...`
    for the HTTP+JSON binding. Only the operations A2A 1.0 defines are forwarded, to the
    interface the card lists, with the credential of the registry. A rule pack
    (`rulepacks/a2a`) decides: an agent whose card was altered is not called, and a
    push notification configuration is not created through the proxy. Each call is in
    the table `invocation` and in the audit log, without what was said. New server
    role, `a2a`.
  - Seven scan rules about tools and agents (scan pack `2026.10.2`): a legacy-only MCP
    server, an agent that cannot be governed, a card that is invalid or not verified, a
    server or an agent that belongs to no declared system, calls that no grant allowed,
    and calls to what no catalogue holds. The scanner reads the catalogues through a
    new port, `TargetDirectory`.
  - A presentation for people who are not developers, in Italian and in English:
    `docs/presentation/`.
  - Semantic detection of personal data
    ([ADR-0055](docs/adr/0055-semantic-pii-detection-as-an-optional-plugin.md)): an
    optional detector, `presidio`, adds names and places written in words to the
    built-in formats, with Presidio and spaCy run in the process. New optional extra
    `pii`; new setting `redaction.detector_settings`. Precision, recall and time are
    measured by `scripts/measure_pii.py` on the labelled sentences of `evaluation/pii/`
    and published in `docs/pii-evaluation.md`.
  - `arbiter demo tour`: a guided demonstration in one command and one process. It
    loads the scenarios, sends requests through the gateway with the mock provider,
    calls a stand-in MCP server and a stand-in agent through the proxies, scans and
    verifies the audit chain. No network and no real model.
  - The answer to `tools/list` shows a caller only the tools its grants let it call
    (`mcp.filter_tool_list`, on by default).
  - The test suite joins the client and a server of the official A2A SDK through the
    proxy, on both bindings.
  - `arbiter demo tour --case consulting`: an invented IT consulting firm, in a tenant
    of its own, that approved one family of models. Its internal regulation is a
    policy pack on top of the default one; its declared tools are allowed on the
    approved model and refused on another engine. `--report FILE` writes the run as a
    self-contained page that tells it as the story of one day: the rule, the people,
    one scene on each screen with what the person does and what Arbiter does, then
    tool by model with what went through and what was refused, the findings and
    the audit chain.
    `scripts/build_demo_pages.py` writes the pages the site serves, from real runs.
    `docs/demo.md` is the script of a live session
    ([ADR-0056](docs/adr/0056-a-demonstration-for-an-it-consulting-firm.md),
    [ADR-0060](docs/adr/0060-the-consulting-case-around-one-approved-model.md)).
  - Reports as PDF: `arbiter report system KEY --format pdf -o DIR` and
    `arbiter report audit --format pdf -o DIR`, with the optional extra `pdf`
    ([ADR-0057](docs/adr/0057-pdf-reports-as-an-optional-extra.md), which supersedes
    ADR-0044). The converter fetches nothing.
  - A declaration may list several projects (`project_ids`), and a key tied to no
    system belongs to the one system that names its project: its tier, budgets and
    grants apply ([ADR-0059](docs/adr/0059-a-system-names-several-projects.md),
    migration 0011).
- **Improvements after Phase 4b.**
  - `GET /api/v1/candidates` and `POST /api/v1/digests/deliveries`: discovery and digest
    delivery over HTTP.
  - `arbiter budgets create`, `list` and `delete`: budgets from the command line.
  - `scripts/check_legal_sources.py`: retrieves the legal sources of a rule pack again
    and compares their checksums
    ([ADR-0034](docs/adr/0034-legal-text-from-the-publications-office.md)).
  - An English summary of the Phase 0 analysis.
- **Compliance toolkit** (Phase 4). Guide: `docs/compliance.md`.
  - Inventory of AI systems declared in YAML, through the API or the CLI, with their AI
    Act roles ([ADR-0007](docs/adr/0007-ai-act-role-explicit-deployer-first.md),
    [ADR-0022](docs/adr/0022-ai-act-roles-one-to-many.md)); example declarations in
    `examples/systems.yaml`.
  - AI Act rule pack written from the Official Journal texts of Regulation (EU)
    2024/1689 and of the amending Regulation (EU) 2026/1744, pinned by checksum
    ([ADR-0034](docs/adr/0034-legal-text-from-the-publications-office.md)): scope,
    prohibited practices, high-risk by Annex I and by each point of Annex III, the
    Article 6(3) derogation as claimed by the provider
    ([ADR-0036](docs/adr/0036-derogation-recorded-from-the-provider.md)), transparency,
    and the obligations of deployers, each with its provision and application date.
  - Deterministic classifier: an indicative tier that stays undetermined while an
    answer is missing, with the questions to answer listed in stages
    ([ADR-0035](docs/adr/0035-staged-classification-facts.md)); a classification is a
    proposal until a named person confirms or overrides it
    ([ADR-0037](docs/adr/0037-classification-is-a-proposal-until-reviewed.md)).
  - Scanner with thirteen rules over the inventory, the classification and the gateway
    traffic metadata; findings deduplicated by fingerprint, with evidence, a reviewed
    lifecycle, accepted risks that expire and suppressions.
  - Daily digest in Markdown and HTML, in English and Italian, with the head of the
    audit chain.
  - `arbiter worker` delivers outbox events and classifies systems when they are
    declared or changed; `arbiter retention purge` applies the retention periods, with a
    six-month floor for high-risk systems
    ([ADR-0038](docs/adr/0038-retention-defaults-and-purge.md)).
  - The gateway denies the requests of a system classified as a prohibited practice
    (policy pack `2026.10.1`) and can limit deployments and regions by risk tier
    (`router.constraints`).
  - CLI: `arbiter systems apply|list|show|questions|facts|classify|review`,
    `arbiter scan`, `arbiter findings list|show|review`, `arbiter digest run`,
    `arbiter keys create --system`. HTTP: `/api/v1/systems`, `/scans`, `/findings`,
    `/suppressions`, `/digests`.
- Rule engine: three-valued evaluation, in which a rule whose facts are missing is
  reported as open with the facts to ask for next; facts with a stage and a provision;
  severities on outcomes; legal sources with checksums on a pack.
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
- Opt-in tests of the OpenAI-compatible adapter against a real server (`tests/live/`),
  skipped unless an endpoint is named in the environment
  ([ADR-0033](docs/adr/0033-real-models-only-in-manual-checks.md)).
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
    ([ADR-0031](docs/adr/0031-token-counts-unknown-by-default.md));
  - `0.1.0a1` as the first release, without a `0.0.1`
    ([ADR-0032](docs/adr/0032-first-release-is-the-alpha.md));
  - provider adapters checked against real models by hand only; no automated test
    depends on a real model
    ([ADR-0033](docs/adr/0033-real-models-only-in-manual-checks.md));
  - the opening decisions of Phase 4: the source of the legal text, staged
    classification facts, the Article 6(3) derogation, review of classifications,
    retention, and a real provider for demos
    ([ADR-0034](docs/adr/0034-legal-text-from-the-publications-office.md) to
    [ADR-0039](docs/adr/0039-real-provider-for-demos.md));
  - the deferrable items of v0.1 before `0.1.0`, and `0.1.0` only after a legal review
    of the AI Act rule pack
    ([ADR-0040](docs/adr/0040-deferrable-items-before-0-1-0.md),
    [ADR-0041](docs/adr/0041-legal-review-before-0-1-0.md)).

### Changed

- The scanner and discovery read the categories of personal data detected in traffic as
  distinct combinations instead of a sample of 5,000 rows: no category can be missed.
- The message of a missing extra gives the way from a clone first, and the `pip`
  command as "once published".
- The event dispatcher no longer holds a transaction while handlers run: delivery stays
  at least once, and a handler that writes to the database no longer waits on SQLite.
- New base dependency: Jinja2, for the digest templates.
- `.gitleaks.toml`: the secret scan allows the `message_key:` lines of rule packs, which
  its generic rule read as credentials.
- Version `0.1.0a1`; development status Alpha. `0.0.1` was never published and is
  skipped ([ADR-0032](docs/adr/0032-first-release-is-the-alpha.md)).
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

- Budgets were listed with the first characters of their id, which are a timestamp: two
  budgets created together showed the same short id. Short ids are now the last
  characters, as for findings.
- A system name with a `|` or a line break broke the inventory table of the Markdown
  digest. Names are now escaped in table cells.
- A PostgreSQL database URL on an install without the `gateway` extra failed with an
  import error and a traceback. It now reports which extra to install
  ([ADR-0010](docs/adr/0010-single-distribution-with-enforced-boundaries.md)).
- PostgreSQL tests ran, and failed, in an environment without the PostgreSQL driver when
  a test database URL was set, as it is in the dev container. They are now skipped there.
