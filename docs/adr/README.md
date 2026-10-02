# Architecture Decision Records

Format: [MADR](https://adr.github.io/madr/). Process: [ADR-0001](0001-use-madr-for-decision-records.md).
Template: [template.md](template.md).

Accepted ADRs are never edited or deleted. A changed decision is a new ADR that
supersedes the old one.

## Index

| ADR | Title | Status | Phase |
|---|---|---|---|
| [0001](0001-use-madr-for-decision-records.md) | Record decisions as MADR files, never delete them | Accepted | 0 |
| [0002](0002-compliance-first-positioning.md) | Position Arbiter as compliance-first, with its own lean gateway | Accepted | 0 |
| [0003](0003-deterministic-classifier-rules-as-data.md) | Classify deterministically, with rules as versioned data | Accepted | 0 |
| [0004](0004-english-artifacts-localised-outputs.md) | Write artifacts in English; localise user-facing outputs in EN and IT | Accepted | 0 |
| [0005](0005-naming-and-distribution.md) | Name the distribution `ai-arbiter`, keep the brand "Arbiter" | Accepted; the `0.0.1` release replaced by 0032 | 0 |
| [0006](0006-no-web-ui-in-v0-1.md) | Ship no web UI in v0.1; HTML outputs and OpenAPI docs are the visible surface | Accepted | 0 |
| [0007](0007-ai-act-role-explicit-deployer-first.md) | Model the AI Act role explicitly; cover the deployer first | Accepted | 0 |
| [0008](0008-local-only-until-phase-6.md) | Develop locally only until Phase 6; estimate costs and set budget alerts then | Accepted | 0 |
| [0009](0009-v0-1-scope.md) | Scope v0.1 as one vertical slice, split into a core and deferrable components | Accepted, amended | 0 |
| [0010](0010-single-distribution-with-enforced-boundaries.md) | One distribution with extras; module boundaries enforced by tooling | Accepted | 1 |
| [0011](0011-plugins-via-entry-points-and-config.md) | Discover plugins through entry points, activate them only from configuration | Accepted | 1 |
| [0012](0012-unified-declarative-rule-engine.md) | One declarative rule engine in Python for policy, classification and scanning | Accepted | 1 |
| [0013](0013-own-llm-provider-adapters.md) | Thin provider adapters instead of a provider library | Accepted | 1 |
| [0014](0014-pii-detection-built-in-and-pluggable.md) | Built-in PII pattern detectors by default, pluggable for more | Accepted, amended | 1 |
| [0015](0015-postgres-and-sqlite-row-level-tenancy.md) | PostgreSQL and SQLite with one portable schema and row-level tenancy | Accepted, amended | 1 |
| [0016](0016-in-process-events-with-outbox.md) | In-process event bus with transactional outbox; Service Bus in Phase 6 | Accepted | 1 |
| [0017](0017-audit-hash-chain-per-tenant.md) | Chain audit entries per tenant with SHA-256 over canonical JSON | Accepted, amended | 1 |
| [0018](0018-metadata-only-by-default.md) | Persist interaction metadata only; redacted content is an opt-in per system | Accepted | 1 |
| [0019](0019-external-telemetry-ingestion.md) | Ingest external gateway data through source adapters into one canonical record | Accepted | 1 |
| [0020](0020-modular-monolith-with-roles.md) | Modular monolith: one image, started in different roles | Accepted | 1 |
| [0021](0021-i18n-message-catalogs.md) | Localise outputs with keyed YAML catalogues and Babel for formatting | Accepted, amended | 1 |
| [0022](0022-ai-act-roles-one-to-many.md) | Store AI Act roles as a one-to-many relation of the AI system | Accepted | 1 |
| [0023](0023-audit-log-in-shared-core.md) | Place the audit log in the shared core | Accepted | 1 |
| [0024](0024-development-tooling-baseline.md) | Development tooling baseline | Accepted | 2 |
| [0025](0025-docker-free-local-development.md) | Develop locally without Docker; build and test containers in CI only | Accepted, extended by 0026 | 2 |
| [0026](0026-codespaces-development-environment.md) | Develop in GitHub Codespaces with a dev container | Accepted | 2 |
| [0027](0027-pii-detectors-core-and-deferrable.md) | Confirm the v0.1 split; divide the built-in PII detectors between core and v0.1.x | Accepted | 3 |
| [0028](0028-api-keys-hmac-with-pepper.md) | Random API keys with a recognisable format, stored as an HMAC keyed with a pepper | Accepted | 3 |
| [0029](0029-canonical-json-in-house.md) | In-house RFC 8785 canonicaliser without floats for the audit hash | Accepted | 3 |
| [0030](0030-price-catalogue-as-versioned-file.md) | Prices in a versioned YAML catalogue; currency converted only when reporting | Accepted | 3 |
| [0031](0031-token-counts-unknown-by-default.md) | Token counts unknown when a provider returns no usage, with an opt-in estimate | Accepted | 3 |
| [0032](0032-first-release-is-the-alpha.md) | `0.1.0a1` is the first release; `0.0.1` is skipped | Accepted | 3 |
| [0033](0033-real-models-only-in-manual-checks.md) | Provider adapters are checked against real models by hand; no automated test depends on one | Accepted | 3 |
| [0034](0034-legal-text-from-the-publications-office.md) | Legal text from the Publications Office, confirmed by the owner on EUR-Lex | Accepted | 4 |
| [0035](0035-staged-classification-facts.md) | Classification facts asked in stages; a missing answer is never a "no" | Accepted | 4 |
| [0036](0036-derogation-recorded-from-the-provider.md) | The Article 6(3) derogation is recorded as claimed by the provider, not computed | Accepted | 4 |
| [0037](0037-classification-is-a-proposal-until-reviewed.md) | A classification is a proposal until a named person confirms or overrides it | Accepted | 4 |
| [0038](0038-retention-defaults-and-purge.md) | Retention defaults, a six-month floor for high-risk systems, a purge command | Accepted | 4 |
| [0039](0039-real-provider-for-demos.md) | A local model server on demand for demos now, Azure AI Foundry in Phase 6 | Accepted | 4 |

"Amended" means the project owner changed the proposal when accepting it; the ADR text
marks each change with "at acceptance".

## Phase 0: summary

Decided by the project owner on 2026-10-02: ADR-0002 to ADR-0008 (D1–D7 of the
[Phase 0 analysis](../phases/phase-0-analysis.md)). ADR-0001 records the process set by
the brief.

Constraints added by the project owner when deciding:

- A2A and MCP stay on the explicit roadmap for v0.2 (ADR-0002).
- The toolkit must ingest from external gateways through adapters (ADR-0002 → ADR-0019).
- An LLM may only ever suggest, never decide a classification (ADR-0003).
- Digest and reports are localised in EN and IT (ADR-0004 → ADR-0021).
- A `0.0.1` release reserves `ai-arbiter` on PyPI (ADR-0005).
- The AI Act role is an explicit field of the data model (ADR-0007).

## Phase 1: summary

Decided by the project owner on 2026-10-02: ADR-0010 to ADR-0021, plus the three
deviations from the brief (single distribution, audit in core, roles one-to-many), the
last two recorded as ADR-0023 and ADR-0022.

Amendments made at acceptance:

- ADR-0014: the default detectors cover EU and Italian formats (*codice fiscale*,
  *partita IVA*, IBAN, EU phone numbers, identity documents); limits documented clearly.
- ADR-0015: PostgreSQL row-level security in Phase 6, confined to the PostgreSQL adapter.
- ADR-0017: fail-closed by default, configurable per tenant; periodic anchoring of the
  chain head to an external destination before Phase 6.
- ADR-0019: LiteLLM file import in v0.1; push endpoint and Azure API Management in v0.2.
- ADR-0021: gettext `.po` noted as the future alternative if translators join.

Other decisions of the project owner:

- The owner configures the PyPI trusted publisher and triggers the `0.0.1` release.
- AI Act sources: the official EU sources on EUR-Lex, verified before Phase 4, including
  the status of any pending change to the application calendar.

## Phase 2: summary

Scaffolding implemented; see the [Phase 2 summary](../phases/phase-2-scaffolding.md).

Decided by the project owner on 2026-10-02:

- ADR-0024 (tooling baseline) and ADR-0025 (Docker-free local development) accepted
  without changes. Both had been applied ahead of acceptance.
- ADR-0026: development moves to GitHub Codespaces with a dev container (Python 3.12,
  3.13 and 3.14, uv, Docker-in-Docker, PostgreSQL). Neither Docker nor uv will be used on
  the corporate machine. ADR-0026 extends ADR-0025: running without containers stays a
  supported path, and containers are now verified in Codespaces as well as in CI.
- Author name: "ViciusLio" in package metadata and `NOTICE`; repository at
  <https://github.com/ViciusLio/ai-arbiter>.
- Azure subscription and budget (ADR-0008) stay open until Phase 6.
- Phase 3 does not start yet. It will start in Codespaces, after the environment and the
  unverified parts of Phase 2 have been checked there.
- ADR-0009 (v0.1 scope) accepted with one change: v0.1 is split into a core that `0.1.0`
  cannot ship without (proxy with FinOps and audit, classifier, findings, digest, CLI, and
  what they depend on) and components that may slip to v0.1.x (among them routing by risk
  class, the LiteLLM importer and the simulation scenarios).

## Phase 3: decisions at the start

Decided by the project owner on 2026-10-02, each from an option table with a
recommendation; in every case the recommended option was chosen.

- Q1 closed by ADR-0027: the split of ADR-0009 is confirmed, and the built-in PII
  detectors are divided between the core and v0.1.x.
- ADR-0028 to ADR-0031: API keys, canonical JSON, price catalogue, token counts.
- The owner approved Phase 2 by giving the go-ahead for Phase 3.

## Phase 3: summary

The core of the gateway is implemented; see the
[Phase 3 summary](../phases/phase-3-gateway.md). No decision was taken during the
implementation beyond the five above. Where the code differs from the Phase 1 sketches is
listed at the top of [interfaces](../architecture/interfaces.md) and of the
[data model](../architecture/data-model.md); none of those differences changes an
accepted decision.

Decided by the project owner on 2026-10-02, at the end of the phase:

- Phase 3 is approved. Phase 4 starts, with its opening decisions brought first.
- ADR-0032: the version becomes `0.1.0a1` and `0.0.1` is skipped (closes Q6).
- ADR-0033: the OpenAI-compatible adapter is checked by hand against a local model
  server; no automated test or CI job may depend on a real model (closes Q5 for that
  adapter; Azure OpenAI waits for Phase 6).
- Working rules for the Codespace, recorded in `CLAUDE.md` under "Codespaces hygiene".

## Phase 4: decisions at the start

Decided by the project owner on 2026-10-02 from the option tables of the
[Phase 4 preparation](../phases/phase-4-preparation.md); in every case the recommended
option was chosen: ADR-0034 to ADR-0039.

## Phase 4: summary

The core of the compliance toolkit is implemented; see the
[Phase 4 summary](../phases/phase-4-compliance.md). No decision was taken during the
implementation beyond ADR-0034 to ADR-0039. Routing constraints by risk class, the first
deferrable item of ADR-0009, were implemented in this phase.

## Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | Closed on 2026-10-02 by ADR-0027 | - |
| Q2 | Azure subscription available, and indicative monthly budget (ADR-0008). The owner will decide by Phase 6 | Phase 6 |
| Q3 | The owner's spot check on EUR-Lex of the articles the AI Act rule pack quotes (ADR-0034). Until then the pack carries `review: pending` | The `0.1.0` release |
| Q7 | Closed on 2026-10-02 by ADR-0034 to ADR-0039 | - |
| Q8 | The CodeQL alert list cannot be read with the Codespace token; Dependabot alerts are disabled for the repository. Both are for the owner to look at | - |
| Q9 | Whether `0.1.0` waits for a review of the AI Act rule pack by a person with legal training, and what comes next: Phase 5 (A2A and MCP) or a v0.1.x phase for the deferrable items of ADR-0009 | Planning |
| Q4 | Closed on 2026-10-02: the dev container, Dockerfile, Compose stack, PostgreSQL tests, Python 3.12 and the CI workflows all ran and passed ([Phase 2 summary](../phases/phase-2-scaffolding.md)). Left: the release workflow has never run, and the CodeQL alert list has not been read | The `0.0.1` release |
| Q5 | Closed on 2026-10-02 by ADR-0033 for the OpenAI-compatible adapter. The Azure OpenAI adapter is checked against a real endpoint in Phase 6 | Phase 6 |
| Q6 | Closed on 2026-10-02 by ADR-0032 | - |

## Deferred decisions

| Topic | When |
|---|---|
| Anchoring sink details for the audit chain | v0.1.x, with external anchoring (ADR-0009) |
| A2A and MCP module design, MCP revision support matrix | Phase 5 |
| IaC tool (Bicep preferred by the brief), networking, identity, signed audit checkpoints, row-level security, container image scanning | Phase 6 |
| Web dashboard | After v0.1 |
