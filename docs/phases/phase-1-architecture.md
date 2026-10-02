# Phase 1: Architecture

- **Status**: closed on 2026-10-02. ADR-0010 to ADR-0021 accepted, four of them amended;
  the three deviations approved (ADR-0010, ADR-0022, ADR-0023). ADR-0009 was accepted
  later the same day, amended. Details in the [ADR index](../adr/README.md)
- **Date**: 2026-10-02
- **Inputs**: [project brief](../PROJECT_BRIEF.md), [Phase 0 analysis](phase-0-analysis.md),
  ADR-0001 to ADR-0008
- **Expected output from the project owner**: decisions on ADR-0009 to ADR-0021 and on
  the open questions in the [ADR index](../adr/README.md)

No code was written in this phase.

## Tasks

| Task | Result |
|---|---|
| Record the Phase 0 decisions as ADRs | ADR-0001 to ADR-0008 accepted; ADR-0009 proposed |
| Start the changelog | [CHANGELOG.md](../../CHANGELOG.md) |
| Monorepo structure and import rules | [Overview](../architecture/README.md), section 3 |
| Component and topology diagrams | [Overview](../architecture/README.md), sections 2 and 4 |
| Flow diagrams | [Flows](../architecture/flows.md): six diagrams |
| Data model | [Data model](../architecture/data-model.md): three ER diagrams, retention table |
| Module interfaces | [Interfaces](../architecture/interfaces.md): ports, decision envelope, events, HTTP and CLI surface |
| Threat model, first pass | [Overview](../architecture/README.md), section 6 |
| ADRs for the main choices | ADR-0010 to ADR-0021, proposed |
| Decision index and open questions | [ADR index](../adr/README.md) |

## What was verified

| Check | Result |
|---|---|
| `ai-arbiter` on PyPI | Not found (free) on 2026-10-02 |
| `arbiter-ai` on PyPI | Exists: 0.2.0, PydanticAI evaluation framework |
| PyPI policy on placeholders | PEP 541 treats empty packages as name squatting; the `0.0.1` release must have real, if minimal, functionality |
| OpenTelemetry GenAI conventions | Still in Development status and moved to a dedicated repository; not suitable as an internal contract |
| LiteLLM log format | A documented standard logging payload exists for callbacks |
| Azure APIM LLM logging | Token metrics policy and a dedicated log table exist |

All eleven Mermaid diagrams were parsed with the Mermaid library to check their syntax.
The architecture itself is untested: no prototype was built in this phase.

## Proposed decisions at a glance

| ADR | Recommendation | Main trade-off |
|---|---|---|
| 0009 | v0.1 is one vertical slice across both products | Every module is thinner than the brief describes |
| 0010 | One distribution with extras; boundaries enforced by a linter | Boundaries are checked in CI, not by packaging |
| 0011 | Entry points for discovery, configuration for activation | Editable install needed in development |
| 0012 | One declarative Python rule engine for policy, classifier and scanner; OPA possible later | Less expressive than Rego; own format |
| 0013 | Own thin adapters for the OpenAI wire format | Narrow provider coverage |
| 0014 | Built-in pattern detectors by default; Presidio and Azure as plugins | Low recall on names and free text by default |
| 0015 | PostgreSQL and SQLite, one schema, `tenant_id` on every row | No PostgreSQL-only features in shared code |
| 0016 | In-process bus with outbox; Service Bus in Phase 6 | Real broker behaviour exercised late |
| 0017 | Per-tenant hash chain, fail-closed | Not tamper-proof against a database administrator until signed checkpoints |
| 0018 | Metadata only; redacted content as an opt-in per system | Content-based scan rules unavailable by default |
| 0019 | Canonical record with source adapters; LiteLLM file import in v0.1 | Adapters track third-party formats |
| 0020 | Modular monolith with roles | Shared release cadence |
| 0021 | Keyed YAML catalogues, Babel for formatting | No translator tooling for the format |

## Changes from the Phase 0 orientation

1. **Packaging.** Phase 0 leaned towards a multi-package uv workspace. With one PyPI name
   fixed by ADR-0005, a single distribution with extras is simpler and keeps the same
   boundary through import rules (ADR-0010).
2. **Audit placement.** The brief lists audit as a gateway module. It is proposed in the
   shared core, because the offline CLI makes classification and finding decisions that
   must be audited without the gateway.
3. **AI Act role cardinality.** ADR-0007 asks for an explicit field. The data model
   proposes a one-to-many relation, since one organisation can be provider and deployer
   of the same system.
4. **One rule engine, three users.** Phase 0 treated the policy engine as a gateway
   question. ADR-0003's "rules as data" applies equally to the classifier and scanner, so
   a single engine is proposed for all three.

## What remains

- Decisions on the proposed ADRs and open questions.
- Primary-source verification of the AI Act dates (before Phase 4).
- Everything else: Phase 2 starts with the repository, tooling, CI, Docker Compose, the
  core package skeleton, configuration and the `0.0.1` release workflow.

## Proposed Phase 2 task list

For orientation; it will be confirmed when Phase 2 starts.

1. `git init`, `.gitignore`, licence, initial Conventional Commit.
2. `pyproject.toml` with extras, uv lock, ruff, mypy strict, pytest with coverage gate,
   import-linter contracts.
3. Package skeleton for `core` with config, ports, plugin registry, persistence base,
   event bus, telemetry bootstrap; first Alembic migration.
4. CLI skeleton with `arbiter --version` and `arbiter init`.
5. Docker image and Compose file: application, PostgreSQL, Mailpit, mock provider.
6. GitHub Actions: lint, type-check, tests on Linux and Windows, both databases,
   dependency and secret scanning, image build.
7. Release workflow with PyPI Trusted Publishing; `0.0.1` prepared, not published.
8. Update `CLAUDE.md` with the real commands; changelog; phase summary.

---

*Arbiter is a support tool and does not provide legal advice.*
