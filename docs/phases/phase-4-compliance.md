# Phase 4: Compliance MVP

- **Status**: core implemented on 2026-10-02 and approved by the project owner the same
  day. The comparison with EUR-Lex is postponed (the pack stays `review: pending`);
  `0.1.0` waits for a legal review of the pack (ADR-0041); Phase 4b follows (ADR-0040)
- **Date**: 2026-10-02
- **Inputs**: [Phase 4 preparation](phase-4-preparation.md) (legal text verified,
  decisions P4-1 to P4-6), ADR-0034 to ADR-0039, the gateway of Phase 3
- **Expected output from the project owner**: approval of the phase; the spot check of
  the quoted articles on EUR-Lex (ADR-0034); the decisions under "Open questions"
- **Target release**: `0.1.0`. Not tagged, not published; the version is still `0.1.0a1`

> Arbiter is a support tool and does not provide legal advice. Nobody with legal training
> has reviewed the rule pack.

## Decisions taken before the code

| ADR | Decision |
|---|---|
| [0034](../adr/0034-legal-text-from-the-publications-office.md) | The legal text comes from the Publications Office by CELEX number, pinned by checksum; the owner confirms the quoted articles on EUR-Lex |
| [0035](../adr/0035-staged-classification-facts.md) | Facts are asked in stages; a missing answer is never a "no" |
| [0036](../adr/0036-derogation-recorded-from-the-provider.md) | The Article 6(3) derogation is recorded as claimed by the provider, not computed |
| [0037](../adr/0037-classification-is-a-proposal-until-reviewed.md) | A classification is a proposal until a named person confirms or overrides it |
| [0038](../adr/0038-retention-defaults-and-purge.md) | Retention defaults, a six-month floor for high-risk systems, a purge command |
| [0039](../adr/0039-real-provider-for-demos.md) | A local model server on demand for demos; Azure AI Foundry in Phase 6 |

No further decision was needed during the implementation.

## Tasks

| # | Task | Result |
|---|---|---|
| 0 | Rule engine | Three-valued evaluation with the facts to ask for next; facts with stage and provision; severities; legal sources with checksums and review state on a pack |
| 1 | Inventory | `ai_system` and `ai_system_role`; declarations in YAML with shared fact sets; unknown facts and wrong types refused; `SystemDeclared` and `SystemChanged` events; the foreign key from API keys |
| 2 | AI Act rule pack | 64 facts, 49 rules, 9 obligations of deployers of high-risk systems; every rule cites its provision and application date; questions and outcomes in English and Italian |
| 3 | Classifier | Pure function of pack, facts and roles; tier, obligations, missing facts; stored immutably with its trace; audited as a decision |
| 4 | Review | Confirm or override with a reason, as a separate record; shared pattern with findings |
| 5 | Scanner | 13 scan rules over declaration, classification and 30 days of traffic metadata; severity lowered while an obligation does not apply yet |
| 6 | Findings | Fingerprint and deduplication, evidence, lifecycle with reviews, accepted risks that expire, suppressions by finding, system or rule, feedback per rule |
| 7 | Digest | Model built from the database; Markdown and HTML through Jinja2; English and Italian; the audit head printed |
| 8 | Worker | `arbiter worker` delivers the outbox; systems are classified when declared or changed |
| 9 | Retention | `arbiter retention purge`, with `--dry-run`, the six-month floor and one audit entry |
| 10 | Link to the gateway | `SystemDirectory` port; policy denies a system classified as prohibited; `router.constraints` by risk tier. This is the first deferrable item of ADR-0009 |
| 11 | CLI and HTTP | Eighteen commands and sixteen endpoints for the above |

## What landed in the core and what moved to v0.1.x

| Item of ADR-0009 | State |
|---|---|
| inventory: systems declared through YAML, API or CLI, with their AI Act roles | Done |
| classifier: versioned rule pack; out of scope, prohibited, high-risk (Art. 6, Annex III, Art. 6(3) derogation), transparency (Art. 50), minimal; rationale, articles, application dates | Done. "Verified against EUR-Lex" is done against the same texts from the Publications Office; the owner's check on EUR-Lex is pending |
| scanner: a first set of high-precision rules over the inventory and gateway traffic metadata | Done: 13 rules |
| findings: full model, state machine with human review through CLI and API, suppressions | Done |
| daily_digest: Markdown and HTML, in English and Italian, produced by a CLI command | Done |
| CLI and API for all of the above; curated OpenAPI documentation | Done |
| Deferrable: routing constraints by risk class | Done in this phase |
| Deferrable: LiteLLM and JSONL importers; simulation scenarios; discovery from traffic; remaining scanner rules; reports; digest by SMTP; local agent | Not started |
| Deferrable from Phase 3: post-call policy, external anchoring, opt-in content store, further PII detectors | Not started |

## What was verified, and how

All in the dev container in GitHub Codespaces, on 2026-10-02.

| Check | Result |
|---|---|
| `scripts/check.sh --containers` | Passes to the end, exit status 0, with the image build and the Compose smoke test |
| Test suite, all extras, Python 3.12, 3.13, 3.14 | 795 passed on each, 4 skipped (the opt-in live tests); the database tests run on SQLite and PostgreSQL |
| Coverage | 98% of the package (gate: 80%) |
| Test suite without extras | 524 passed, 140 skipped (PostgreSQL variants and tests that need the web stack) |
| `ruff`, `mypy` strict, `lint-imports` | Clean. The contract "gateway and compliance never import each other" now exempts `gateway.api`, the composition root, as the architecture overview describes |
| Legal text | Read from the three documents listed in the preparation document; application dates in the pack are checked by a test against Article 113 as amended |
| Classifier against the real pack | Each exclusion of Art. 2, each prohibited practice, Annex I, Annex III, the derogation with and without profiling, each transparency case, the obligations that depend on who the deployer is |
| "A missing answer is never a no" | Tested in the engine and in the classifier: a partly answered system is `undetermined`, and the details of an area are not asked before the area |
| The seven example systems | Declared, classified and scanned on SQLite and PostgreSQL; expected tiers and findings asserted one by one |
| Findings lifecycle | Every allowed and refused move; reopening on a new detection; expiry of an accepted risk; suppressions by scope and with expiry; closure when the cause is fixed |
| Digest | Empty tenant, full example, Italian, HTML with a hostile system name escaped |
| Privacy | Audit entries and digest run records hold no system or person names; a review is recorded under a principal id |
| Tenant isolation | Inventory, findings and their HTTP endpoints, with two tenants |
| Gateway link | Through the HTTP application: a key tied to a prohibited system is denied; a high-risk system is routed only to the allowed region, and the excluded deployment is in the audited decision |
| The acceptance criterion of ADR-0009, by hand | The six steps with a real server process, from `arbiter init` to the digest in Italian: 16 seconds |
| CI on GitHub | Green on the last commit of the phase, on every job. The runs of the intermediate commits were cancelled by the pushes that followed them, as the workflow is configured to do |

### Not verified

| Item | Why |
|---|---|
| The legal correctness of the rule pack | Written by an AI assistant from the primary text; not reviewed by a person with legal training. The questions are summaries, in two languages, of provisions that are longer and more qualified |
| The quoted articles on the EUR-Lex website | The site refuses automated access. Pending with the owner (ADR-0034) |
| Corrigenda and later amending acts | None found under the usual identifiers and by web search; the legislative observatories were not consulted |
| Precision and recall of the scan rules | Seven hand-written examples are not a measurement |
| `arbiter worker` as a long-running process | Tested with `--once`; the loop with a sleep was not left running |
| The digest in a mail client | HTML rendered and checked as text; not opened in a browser or a mail client |
| Large inventories and long periods | The scanner reads up to 5,000 interactions per system for PII categories; nothing was measured with volume |
| Azure OpenAI adapter, hosted providers, release workflow, CodeQL alert list | As at the end of Phase 3 |

## Things that turned out differently from the design

The complete list is at the top of [interfaces](../architecture/interfaces.md) and of the
[data model](../architecture/data-model.md). The ones that matter:

- **Questions are not declared with their dependencies.** The preparation proposed that
  a detailed fact names the area it depends on. The three-valued evaluation made that
  unnecessary: the engine reports which facts an undecided rule needs next, and an area
  answered "no" settles its details. The pack stays simpler.
- **The date is not an input of the classifier.** A classification does not change with
  the calendar; each obligation carries the date it applies from, and whether it applies
  today is decided when it is shown. The scanner lowers the severity of a finding whose
  obligation is still in the future.
- **The scanner closes findings.** The designed lifecycle had only people moving a
  finding to `mitigated`. A finding whose cause is fixed would otherwise stay open
  forever, so the scanner marks it as mitigated when it is no longer detected, and
  records that it did.
- **`gateway.api` imports the compliance toolkit.** The architecture always drew the
  HTTP application as serving both halves; the import rule now says so explicitly.
- **The event dispatcher holds no transaction while handlers run.** On SQLite a handler
  that wrote to the database waited for the dispatcher until it timed out.
- **`verified_against` and `review` are two fields.** The pack was written from the
  primary text (`verified_against: primary`) and waits for the owner's check
  (`review: pending`); calling it "secondary" would have been wrong.

## Defects found while building

- Two rules asked their questions too early: the derogation and the fundamental rights
  assessment were asked of systems outside Annex III. Found by the tests of the
  classifier; the conditions now start from the Annex III point.
- The event dispatcher deadlocked on SQLite (see above). Found by the worker test.
- A test of mine set an enumeration field to a plain string; fixed in the test.
- The secret scan in CI failed on sixteen lines of the rule pack: it read
  `message_key: aia...` as a credential. They are identifiers. `.gitleaks.toml` now allows
  exactly those lines; the scan was not run locally before those pushes, against the
  project's own rule, and that is why it was found late.
- The codespace stopped by itself in the middle of a test run, with uncommitted work on
  disk. Nothing was lost; the hand-over now records progress item by item and work is
  pushed at every step.

## Open questions

See the [ADR index](../adr/README.md).

1. Q3: the owner's spot check on EUR-Lex. The articles the pack quotes: 2, 3(1), 4, 5,
   6, 26, 27(1), 49(2), 50, 111, 113 and Annex III.
2. Whether `0.1.0` waits for a review of the rule pack by a person with legal training
   (improvement I-22), and who that would be.
3. Which deferrable items come before `0.1.0`, if any: importers, discovery from
   traffic, reports, e-mail delivery, simulation scenarios.
4. Q2: Azure subscription and budget, by Phase 6.

## Proposed Phase 5 task list

A2A and MCP (v0.2), from the roadmap. For orientation; confirmed when the phase starts.
Decisions to bring first: the MCP revisions to support and how; A2A through the official
SDK and what Arbiter adds (registry, authorisation, card signature checks, audit); where
the MCP proxy sits relative to the gateway.

Before that, the owner may prefer a `0.1.x` phase for the deferrable items of v0.1.

---

*Arbiter is a support tool and does not provide legal advice.*
