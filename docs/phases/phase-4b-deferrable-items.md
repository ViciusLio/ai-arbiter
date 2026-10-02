# Phase 4b: Deferrable items of v0.1

- **Status**: implemented on 2026-10-02 and approved by the project owner the same day.
  Phase 5 (A2A and MCP) opens with its decisions; improvements that need no decision are
  made alongside and recorded in the README
- **Date**: 2026-10-02
- **Inputs**: ADR-0040 (this phase before Phase 5), ADR-0009 (the deferrable items),
  the compliance toolkit of [Phase 4](phase-4-compliance.md)
- **Expected output from the project owner**: approval of the phase, and the go-ahead
  for Phase 5 (A2A and MCP)
- **Target release**: `0.1.0`. Not tagged, not published; the version is still `0.1.0a1`

> Arbiter is a support tool and does not provide legal advice. Nobody with legal training
> has reviewed the rule pack.

## Decisions

Importers, reports and e-mail delivery followed decisions already taken (ADR-0009,
ADR-0011, ADR-0019, ADR-0025). Four were brought to the owner during the phase:

| ADR | Decision |
|---|---|
| [0042](../adr/0042-discovered-systems-by-project.md) | A system discovered from traffic is identified by its project; a candidate is a proposal |
| [0043](../adr/0043-simulation-scenarios-as-data.md) | Scenarios are YAML files loaded into a tenant of their own and checked by tests |
| [0044](../adr/0044-reports-without-pdf.md) | Reports in Markdown and HTML; PDF by printing the HTML |
| [0045](../adr/0045-smtp-checked-against-the-compose-mail-catcher.md) | The SMTP notifier is checked against Mailpit in the Compose check |

Choices made while implementing, within those decisions, that the owner may want to
revisit:

- The default notifier is `file`: `--send` writes `.eml` files until an operator names
  `smtp`. A digest holds names of systems and findings, so nothing leaves by default.
- An imported record keeps the team it came from (`interaction.source_group`), never
  the alias of the key, which can be the name of a person.
- A declared system that names its project counts the unattributed requests of that
  project as its own, at read time. Stored interactions are not rewritten, so the usage
  totals by system do not change.
- Simulated requests are stored with the source `simulation` and are not in the usage
  totals.
- ADR-0044 departs from the brief, which lists PDF among the report formats.

## Tasks

| # | Task | Result |
|---|---|---|
| 1 | Importers | `InteractionRecord` as the canonical record and JSONL format; `TelemetrySource` port; sources `jsonl` and `litellm`; `arbiter ingest`; attribution by tag or by configured mapping; idempotent on the source's record id; content dropped on the way in |
| 2 | Reports | System report and audit report, Markdown and HTML, English and Italian; `arbiter report system KEY`, `arbiter report audit`; `GET /api/v1/systems/{key}/report`, `GET /api/v1/audit/report` |
| 3 | Digest by e-mail | `Notifier` port; notifiers `file` and `smtp` on the standard library; `arbiter digest run --send`, one message per language; one audit entry per delivery, without addresses |
| 4 | Discovery | Candidates per project, or per group of an imported source; scan pack `2026.10.1` with `SCAN-UNDECLARED-SYSTEM-CANDIDATE`; `arbiter systems discover` and `--draft`; migration 0007 |
| 5 | Scenarios | Three scenarios of eight invented systems, each with expected tier and findings; `arbiter demo list`, `arbiter demo run`; run by the test suite |
| 6 | Print style sheet | In the HTML reports and the HTML digest |
| 7 | Mail check | `scripts/smoke-mail.sh`, a step of `scripts/check.sh --containers` and of the container job in CI |

## What was verified, and how

All in the dev container in GitHub Codespaces, on 2026-10-02.

| Check | Result |
|---|---|
| `scripts/check.sh --containers` | Passes to the end, exit status 0, at commit `cdf71ff` |
| Test suite, all extras, Python 3.12, 3.13, 3.14 | 930 passed on each, 4 skipped (the opt-in live tests); the database tests run on SQLite and PostgreSQL |
| Coverage | 98% of the package (gate: 80%) |
| Test suite without extras | 623 passed, 173 skipped (PostgreSQL variants and tests that need the web stack) |
| `ruff`, `mypy` strict, `lint-imports`, the em-dash check | Clean; 4 import contracts kept |
| Secret scan on each staged change | No leaks, with the gitleaks command of CI |
| SMTP notifier against Mailpit, in the Compose stack | `arbiter digest run --send` in the application container sent 2 of 2 messages; the Mailpit API held both, in English and in Italian; the audit chain verified afterwards |
| Scenarios in the application container, on PostgreSQL | `arbiter demo run --all`: the eight systems and the two candidates as the scenarios expect |
| Every scenario in the test suite | Expected tier and findings of each system, the candidates, no other finding, the audit chain; on SQLite and PostgreSQL |

Not verified:

| Item | Why |
|---|---|
| The LiteLLM importer against a live LiteLLM | Written from its documented specification; the samples in `examples/` were built from that specification (I-31) |
| `arbiter report`, `arbiter systems discover`, `arbiter ingest`, run by hand | They were run by the test suite only, through the command line runner; the output was never read by a person |
| SMTP with STARTTLS, TLS or authentication | Mailpit in the stack accepts plain SMTP; those paths are covered by tests that replace the client |
| How the HTML reports print | The print style sheet was written and never printed |
| The legal correctness of the rule pack; the quoted articles on EUR-Lex | As at the end of Phase 4 (ADR-0041, ADR-0034) |

## Defects found while building

- Two scenarios declared a system with the same key in different ways: loaded together,
  one rewrote the other. Scenario keys and groups are now unique, and a test checks it.
- A record whose cost was not a number crashed the canonical record instead of being
  refused. Fixed with the importers.
- A manual check ran `arbiter init` in the root of the repository by mistake. The files
  it wrote were ignored by git and were removed. Two rules followed, in `CLAUDE.md`: no
  `rm` with a glob or a variable inside the repository, and manual checks as short,
  separate commands in a directory made by `mktemp -d`.

## Limits

- The LiteLLM importer follows the specification LiteLLM documents for its standard
  logging payload, read on 2026-10-02. It was not run against a live LiteLLM.
- A candidate is as coarse as a project. A candidate from imported records stays until
  those records leave the 30-day window, even after its system is declared.
- The gateway applies the tier of a system only to keys tied to it, not to every key
  of the project the system names.
- `systems discover` and `digest --send` exist on the command line only.
- The scenarios are three, and their expected outcomes were written by the author of
  the rules: they catch a rule that changes, not a rule that is wrong.
- No PDF output.

---

*Arbiter is a support tool and does not provide legal advice.*
