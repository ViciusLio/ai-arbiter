# Phase 3: Gateway MVP

- **Status**: core implemented on 2026-10-02; waits for the approval of the project
  owner. The deferrable components of ADR-0009 are not started
- **Date**: 2026-10-02
- **Inputs**: ADR-0009 to ADR-0026, the Phase 3 task list of the hand-over, the
  environment verified in Codespaces
- **Expected output from the project owner**: approval of the phase, and the decisions
  listed under "Open questions"
- **Target release**: `0.1.0-alpha`. Not tagged, not published

## Decisions taken before the code

Presented to the owner as option tables with a recommendation; in each case the owner
chose the recommended option.

| ADR | Decision |
|---|---|
| [0027](../adr/0027-pii-detectors-core-and-deferrable.md) | The v0.1 split of ADR-0009 is confirmed. Built-in PII detectors with a checksum or an unambiguous format are in the core; identity documents and the phone and VAT formats of other member states move to v0.1.x. Closes Q1 |
| [0028](../adr/0028-api-keys-hmac-with-pepper.md) | API keys `arb_<key id>_<secret><checksum>`, stored as HMAC-SHA-256 keyed with a pepper that can be rotated |
| [0029](../adr/0029-canonical-json-in-house.md) | In-house RFC 8785 canonical JSON without floats; an independent library is used only by the tests |
| [0030](../adr/0030-price-catalogue-as-versioned-file.md) | Prices in a versioned YAML catalogue with overrides; exact decimals; currency converted only when reporting |
| [0031](../adr/0031-token-counts-unknown-by-default.md) | No usage from the provider means unknown and unpriced; a deployment can opt in to flagged estimates |

No further decision was needed during the implementation.

## Tasks

The ten core items of the hand-over, in the order they were built. Each was committed on
its own, with its tests.

| # | Task | Result |
|---|---|---|
| 1 | Identity | Teams, projects, principals, role bindings scoped to tenant, team or project; API keys per ADR-0028 with pepper rotation; `arbiter init` generates the pepper in `.env` |
| 2 | Rule engine | `core.rules`: pack schema with declared facts, closed operator set, evaluation with a trace per match, the `Decision` envelope; `core.canonical_json` |
| 3 | Audit | `core.audit`: chain per tenant, append under a lock on the chain head, verification, JSONL export and its offline verification, `audit.fail_mode` per tenant; `arbiter audit verify` and `export` |
| 4 | Providers | `LLMProvider` port; plugins `mock`, `openai_compat`, `azure_openai`; settings of each deployment validated by its plugin at startup |
| 5 | Router | Candidates by served model; priority and cost strategies; retry and fallback; the plan and every attempt as a routing decision |
| 6 | FinOps | Price catalogue, metering, daily roll-ups per scope, soft and hard budgets, usage report in Markdown in English and Italian; the `interaction` table as the canonical record of ADR-0019 |
| 7 | Redaction | Eight built-in detector categories (ADR-0027); mask, keyed hash and drop strategies; `arbiter pii detectors` and `redact` |
| 8 | Policy | Fact collection, pre-call evaluation, default pack with three rules; the chat service that joins all of the above in one request path |
| 9 | HTTP | `/v1/chat/completions` with streaming, `/v1/models`; the control plane under `/api/v1`; RFC 9457 errors; `arbiter keys` and `arbiter usage report` |
| 10 | Latency | `scripts/measure_latency.py`, run by `scripts/check.sh` and in CI |

Also done, because the above needed it:

- message catalogues in English and Italian with Babel (`core.i18n`), for the usage
  report and for the reasons of a denial;
- SQLite transactions opened as write transactions, without which concurrent appends to
  the audit chain fail on SQLite;
- the improvements I-03, I-07 and I-09 of the README tracking table.

## What landed in the core and what moved to v0.1.x

ADR-0009 asks each phase to report this item by item.

| Item of ADR-0009 | State |
|---|---|
| identity: tenants, teams, projects, hashed API keys, three roles | Done. Tenants are created from the CLI, not through the API |
| llm_router: chat completions with SSE, models, three adapters, two strategies, fallback and retry | Done |
| finops: metering per tenant, team, project, user and AI system; price catalogue; budgets; usage API and Markdown report | Done |
| policy: model allowlist, budget enforcement, PII detection and redaction on the prompt | Done, with the detector set of ADR-0027 |
| core: rule engine; audit chain, verification, JSONL export; EN and IT catalogues | Done |
| Deferrable: routing constraints by risk class | Not started. Needs the classification of Phase 4 |
| Deferrable: post-call policy evaluation | Not started |
| Deferrable: external anchoring of the audit chain head | Not started |
| Deferrable: opt-in store of redacted content | Not started |
| Deferred by ADR-0027: further detectors, precision and recall | Not started |

## What was verified, and how

All in the dev container in GitHub Codespaces, on 2026-10-02.

| Check | Result |
|---|---|
| `scripts/check.sh --containers` | Passes to the end, exit status 0 |
| Test suite, all extras, Python 3.12, 3.13 and 3.14 | 632 passed on each, none skipped; the database tests run on SQLite and on PostgreSQL |
| Coverage | 98% of the package (gate: 80%) |
| Test suite without extras | 422 passed, 103 skipped (PostgreSQL variants and tests that need the web stack) |
| `ruff`, `mypy` strict, `lint-imports` | Clean; the four import contracts hold with the new packages |
| Canonical JSON | RFC 8785 examples, and equality with the `rfc8785` library on 500 generated values |
| Audit chain | Tampering, removal, truncation and a wrong head are each detected; 25 concurrent writers produce one unbroken chain on both engines; the hash of an entry is recomputed with the independent library |
| The verifier printed in `docs/audit.md` | Run against a real export: verifies |
| Privacy | After requests with an e-mail address in the prompt, a test searches every column of every table for the address and for the prompt text, and finds neither |
| Tenant isolation | Service-level and HTTP-level tests with two tenants: lists, lookups, revocation and usage do not cross |
| Checksum detectors | Fiscal code, IBAN, VAT number and Luhn validators agree with well-known published examples |
| Secret scan | The gitleaks image and command of CI, run locally before pushing |
| Wheel | Built and inspected: rule pack, price catalogue, locale files and the plugin entry points are inside |
| The quickstart, by hand | `arbiter init`, `keys create`, `serve`, then `curl`: a completion with redaction headers, a stream ending in `[DONE]`, 404 for an unknown model, 401 without a key, the audit chain verified through the API, the CLI and from an export file, the usage report in Italian, and a look at the database confirming that no prompt text was stored |
| Image and Compose stack | The image builds and runs as uid 10001; the stack starts, initialises a workspace, and the smoke test creates a key in the container, gets a completion through the published port and verifies the audit chain |
| CI on GitHub | Green on every commit of the phase |

### Latency added by the gateway

`scripts/measure_latency.py`, 300 requests through the real application in process,
against the mock provider, with a prompt of about 800 characters that contains personal
data. 2-core Codespace.

| Database | Concurrency | Mean | p50 | p95 | p99 |
|---|---:|---:|---:|---:|---:|
| SQLite | 1 | 19.7 ms | 18.2 ms | 27.4 ms | 42.8 ms |
| PostgreSQL | 1 | 18.9 ms | 16.9 ms | 26.7 ms | 34.7 ms |
| SQLite | 10 | 165.4 ms | 142.9 ms | 366.4 ms | 473.5 ms |
| PostgreSQL | 10 | 297.5 ms | 293.8 ms | 402.4 ms | 474.3 ms |

One request makes 17 database statements: five reads before the provider is called (key,
project, roles, tenant, budgets) and twelve in the final transaction (interaction, four
roll-ups, two audit entries with their head, the outbox event).

With ten requests in flight for the same tenant, throughput does not rise: the writes of
one tenant are put in order by the audit chain (ADR-0017), and the process is a single
Python event loop. This is one process on one machine with no network hop; it says what
the code costs, not what a deployment will deliver.

### Not verified

| Item | Why |
|---|---|
| `azure_openai` against a real endpoint | No Azure resources before Phase 6 (ADR-0008). Tested against a simulated HTTP transport: URL shape, key header, error mapping |
| `openai_compat` against hosted services | Checked against one local server only, see below. Other OpenAI-compatible services may differ in details |
| Precision and recall of the PII detectors | Needs a labelled data set; planned with the simulation scenarios |
| Behaviour under load, with several processes and a network | Out of reach of a Codespace; planned for the Azure phase |
| A real OpenAI client library against `/v1` | Only `curl` and the test client were used |
| Client disconnection in the middle of a stream over a real socket | The abandoned-stream path is tested by closing the generator, not by dropping a connection |
| Windows | CI runs the suite on Windows; nothing was run there by hand |
| Release workflow, CodeQL alert list | As at the end of Phase 2 |

### Check of the OpenAI-compatible adapter against a real server

Done by hand on 2026-10-02, after the phase was approved (ADR-0033). Ollama 0.35.0 ran as
a container in the Codespace with the model `smollm2:135m` (270 MB), reachable on
`127.0.0.1` only. Prompts were synthetic.

| Check | Result |
|---|---|
| Completion through the adapter | Answer received; usage reported, cached tokens included |
| Stream through the adapter | Text received in chunks; the server honours `stream_options.include_usage`, so the token counts of a stream are measured, not estimated |
| A model the server does not have | HTTP 404, mapped to a provider error |
| The whole gateway in front of it, on SQLite and PostgreSQL | Completion and stream answered; the e-mail address in the prompt was redacted before it left; both interactions recorded with measured token counts |
| `arbiter serve` as a real process, with `curl` | Same, plus: fallback from a deployment with an unreachable endpoint to the working one, recorded attempt by attempt in the routing decision; cost computed from a configured price; 502 with the decision id when the only deployment fails; audit chain verified afterwards |

The same checks are kept as opt-in tests in `tests/live/`, skipped unless
`ARBITER_LIVE_OPENAI_BASE_URL` is set. No CI job sets it.

Not covered by this check: authentication with an API key (the local server needs none;
the header is tested against the simulated transport), rate limiting (429), timeouts,
tool calls, images, and any hosted service.

Afterwards the container, its image (9.3 GB) and the model were removed: 9.55 GB freed,
free space back to what it was before.

## Things that turned out differently from the design

The complete list is at the top of [interfaces](../architecture/interfaces.md) and of the
[data model](../architecture/data-model.md). The ones that matter:

- **The canonical interaction record is in `core`**, not in the gateway: the compliance
  toolkit reads it and the importers of Phase 4 write it, and the two halves may not
  import each other.
- **Money is stored as scaled integers.** SQLite has no decimal type; a `Numeric` column
  would have stored floats there.
- **Roll-ups are per day**, updated in the transaction that records the interaction, not
  by an event handler. Budgets need them current, and nothing dispatches the outbox yet.
- **One event is published**, `InteractionRecorded`. `PolicyDenied` and
  `BudgetThresholdReached` wait for their first consumer in Phase 4.
- **Two audit entries per request**, one per decision (policy, routing), instead of one
  entry holding both. It keeps "one decision, one entry" and costs three statements.
- **No `/api/v1/tenants`.** An API key acts inside its tenant; creating tenants is an
  operator task, done from the CLI.
- **A streamed response cannot fail closed.** It is recorded when it ends; by then the
  client has it. `docs/audit.md` says so.
- **Arbiter ships no prices of real providers.** Decided in ADR-0030: a stale price shown
  as current would mislead.

## Defects found by the tests while building

- The version digest of a price catalogue with overrides failed on prices with a region
  (sorting `None` against strings). Fixed.
- A fake private key in a test fixture was flagged by the secret scan before the commit
  was pushed. Fixtures that look like secrets are now assembled from parts.
- Usage reports showed small costs as `0.0000`. Amounts are now shown with six decimals.

## Open questions

See the [ADR index](../adr/README.md).

1. Q5: credentials for an OpenAI-compatible endpoint, to run the adapters for real
   before `0.1.0`.
2. Q6: the version number to give this state of the code.
3. Q2: Azure subscription and budget, by Phase 6.
4. Q3: verification of the AI Act text and calendar on EUR-Lex, before the rules of
   Phase 4 are written.

## Proposed Phase 4 task list

Compliance MVP. For orientation; confirmed when Phase 4 starts.

1. Verify the AI Act text, the amending acts and the application calendar on EUR-Lex;
   record the verification date (Q3).
2. Inventory: AI systems declared through YAML, API and CLI, with their AI Act roles;
   the `SystemDirectory` port; the foreign key from API keys.
3. Classifier: the versioned AI Act rule pack and the classification as an audited
   decision.
4. Scanner: a first set of rules over the inventory and the interaction metadata.
5. Findings: model, review workflow through CLI and API, suppressions.
6. Daily digest: Markdown and HTML, in English and Italian.
7. The outbox dispatcher (`arbiter worker`) and the events the modules above consume.
8. Routing constraints by risk class, the first deferrable item of ADR-0009, once
   classifications exist.

Decisions to bring first: the fact schema of the AI Act rule pack; how a classification
is reviewed and overridden by a person; the retention defaults (deferred from Phase 1).

---

*Arbiter is a support tool and does not provide legal advice.*
