# CLAUDE.md: Arbiter

AI Governance Gateway & EU AI Act Compliance Toolkit. Open source, Apache 2.0.
Repository: <https://github.com/ViciusLio/ai-arbiter>

This file is the hand-over between sessions. A session in a new environment has no
memory of earlier ones: everything needed to resume is here or linked from here.

## Resume here

**State on 2026-10-05.** Phases 0 to 4b are done and approved. **Phase 5 (A2A and MCP)
is in progress**: the owner decided P5-1 to P5-8 on 2026-10-05, all as recommended
(ADR-0046 to ADR-0053), and left the question of I-20 to the implementer, with security
and compliance first (ADR-0054: no cache of key lookups). The version is `0.1.0a1`, not
published (ADR-0032). `0.1.0` waits for a legal review of the AI Act rule pack
(ADR-0041).

Read first: `docs/phases/phase-4b-deferrable-items.md` (what was built, verified and not
verified), then `docs/compliance.md`, `docs/gateway.md` and `docs/audit.md`.

### Step 1: quick check in a new codespace, or after a restart

`git config user.email` (must be `viciuslios@gmail.com`, local config), `git status`,
`pg_isready -h postgres -U arbiter -d arbiter_test`, then `uv run pytest -q`.

Never run a script of your own against the database of `ARBITER_TEST_DATABASE_URL` while
the test suite is running: the tests migrate and drop its tables.

### Step 2: Phase 5, where it stands

Update this list at every commit.

| # | Item | State |
|---|---|---|
| 1 | Decisions recorded | Done: ADR-0046 to ADR-0054 |
| 2 | MCP catalogue: servers and tools, tied to declared AI systems (`gateway/mcp`) | Not started |
| 3 | MCP proxy: Streamable HTTP, revision `2026-07-28` only, allowlist, an audit entry per call without arguments; `mcp-types` as an optional extra | Not started |
| 4 | A2A registry: cards fetched, stored, verified against configured keys (`a2a-sdk[signing]` behind a port, in `adapters`) | Not started |
| 5 | A2A proxy for JSON-RPC and HTTP+JSON, with authorization and audit; gRPC not proxied | Not started |
| 6 | Findings: undeclared servers and agents, tools outside the allowlist, unverified cards, legacy-only servers | Not started |
| 7 | Demo with mock agents and a mock MCP server (no real model) | Not started |
| 8 | Phase summary, README tracking, changelog, `scripts/check.sh --containers` (dependencies change) | Not started |

Checked on the installed packages on 2026-10-05: `mcp-types` 2.2.0 depends only on
Pydantic and `typing-extensions`; modules `jsonrpc`, `methods`, `version`; constants
`LATEST_PROTOCOL_VERSION` (`2026-07-28`), `MODERN_PROTOCOL_VERSIONS`,
`PROTOCOL_VERSION_META_KEY`, error code `-32022`. `a2a-sdk[signing]` 1.2.1:
`a2a.utils.signing.create_signature_verifier(key_provider, algorithms)`, where
`key_provider(kid, jku)` returns the key; the extra adds PyJWT.

Phase 4b delivered: importers (`compliance/ingest`, `arbiter ingest`), reports
(`compliance/reports`, `arbiter report`), digest by e-mail (`core/notification.py`,
`adapters/local/notifiers.py`, `compliance/digest/delivery.py`, `digest run --send`),
discovery (`compliance/inventory/discovery.py`, scan pack `2026.10.1`,
`systems discover`, migration 0007), scenarios (`src/ai_arbiter/scenarios/*.yaml`,
`compliance/simulation`, `arbiter demo`; keys and groups unique across scenarios),
`scripts/smoke-mail.sh` in the container check. Logs of long local runs go to
`.check-logs/`, ignored by git.

### Step 3: for the owner, not blocking

Q10: find the person who reviews the rule pack (ADR-0041). Q3: spot check on EUR-Lex of
the articles the pack quotes (2, 3(1), 4, 5, 6, 26, 27(1), 49(2), 50, 111, 113, Annex
III); when done, set `review: confirmed` and `review_date` in
`rulepacks/ai-act/<version>/pack.yaml`. Publishing `0.1.0a1` (`docs/releasing.md`); the
CodeQL alerts (the Codespace token gets a 403); whether to enable Dependabot alerts;
Azure subscription and budget by Phase 6.

### Step 4: what stays deferrable after Phase 4b

Post-call policy evaluation, external anchoring of the audit head, opt-in store of
redacted content, further PII detectors with measured precision and recall, the local
agent, the remaining scanner rules. Only when the owner asks.

Not verified: the legal correctness of the rule pack; the quoted articles on EUR-Lex
itself; the `azure_openai` adapter against a real endpoint; hosted OpenAI-compatible
services; the release workflow. The README table "Release improvement tracking" lists
every open improvement.

### Step 5: Phase 5 (A2A and MCP, v0.2)

The decisions are taken (ADR-0046 to ADR-0054) and the order of work is in Step 2. The
facts read on the official sources are in `docs/phases/phase-5-preparation.md`.

## Names (ADR-0005)

| Thing | Name |
|---|---|
| Brand | Arbiter |
| Repository; PyPI distribution, once published | `ai-arbiter` |
| Import package | `ai_arbiter` |
| CLI | `arbiter`, alias `ai-arbiter` |
| Author | ViciusLio |

Unrelated to `arbiter-ai` on PyPI. Always write the full distribution name in install
instructions. Version in `pyproject.toml`: `0.1.0a1`, the first release (ADR-0032);
nothing is published yet and the owner publishes (`docs/releasing.md`).

## Git

- Commits are authored as **ViciusLio <viciuslios@gmail.com>**, always. Check
  `git config user.email` before the first commit in a new clone or codespace; if it
  differs, set it in the repository's local config, never globally.
- Conventional Commits. End commit messages with the co-author trailer of the assistant
  that wrote them.
- Work on `main` until the owner asks for branches. Never force-push `main`.

## Reference documents

- `docs/PROJECT_BRIEF.md`: initial requirements, in Italian. Never edited; changes go
  through ADRs.
- `docs/phases/phase-N-*.md`: analysis and summary of each phase
- `docs/gateway.md`, `docs/audit.md`: how the gateway and the audit log work and are
  configured; keep them in step with the code
- `docs/architecture/`: overview, flows, data model, interfaces. The Phase 1 sketches are
  kept as written; each document starts with where the code differs
- `docs/adr/`: decisions (MADR); index and open questions in `docs/adr/README.md`
- `docs/releasing.md`: how a release is published
- `CHANGELOG.md`: Keep a Changelog + SemVer, entries linked to ADRs

## Environment (ADR-0026)

Development happens in the dev container (`.devcontainer/`), in GitHub Codespaces.

- Python 3.12, 3.13, 3.14 installed by uv; 3.12 is the default (`.python-version`).
- Docker-in-Docker: the project image and `deploy/compose/compose.yaml` run inside it.
- PostgreSQL is the sidecar service `postgres`; `ARBITER_TEST_DATABASE_URL` is preset, so
  database tests run on SQLite and PostgreSQL.
- The project Compose stack publishes its own PostgreSQL on `127.0.0.1:5432` of the dev
  container; the test database is on host `postgres`. They do not collide.
- Stop the codespace when idle; it is billed beyond the free allowance.

### Codespaces hygiene

Set by the owner on 2026-10-02. These hold in every session.

- The codespace runs on the free quota (120 core-hours and 15 GB a month). Treat compute
  time and disk space as limited resources.
- Leave nothing running that is not needed: stop `arbiter serve`, development servers and
  the Compose stack (`docker compose ... down --volumes`) as soon as you are done.
- Checks: while working, use `uv run pytest` and targeted checks. Run the full
  `scripts/check.sh` before closing a phase, and `--containers` only at the end of a
  phase or when the Dockerfile, the Compose file or the dependencies change.
- Disk: at the end of a session report `df -h /workspaces` and `docker system df`. If
  unused Docker images exceed 2 GB, propose `docker system prune` to the owner before
  running it.
- Stop the codespace only when the owner writes "chiudiamo", never on your own
  initiative. Then: update "Resume here", commit, push, check that `git status` is
  clean, and try `gh codespace stop -c "$CODESPACE_NAME"`. If that fails for lack of
  permission, say so and remind the owner to stop it from <https://github.com/codespaces>.
- When you stop to wait for the owner's answer, say so plainly in the last line of the
  message: the idle timer of the codespace is running from that moment.
- The codespace also stops by itself after a period without activity of the owner, even
  while a long task is running (it happened on 2026-10-02, in the middle of a test run).
  Files on disk survive; `/tmp`, running processes and containers do not. So: commit and
  push at every working step, keep nothing needed in `/tmp`, and after a restart check
  `git status`, the test database and what was running before going on.
- Billing and account settings are out of reach. When usage needs checking, ask the
  owner to look at <https://github.com/settings/billing>.
- For one-off scripts use `uv run python`, never `python3` or `python3.12`: after a
  restart those may resolve to a system interpreter that lacks the standard library.
- Never run `rm` with a glob or a variable inside `/workspaces/ai-arbiter`. A manual
  check works in a temporary directory created with `mktemp -d`, and only that directory
  is deleted afterwards, by its literal path (set by the owner on 2026-10-02).
- Manual checks are run as short, separate commands, one thing each, never as one long
  chained line: the owner reads each command before approving it.
- Never create another codespace or change the machine type without asking.
- A local model server, when one is needed for a manual check, runs as a container and
  is removed afterwards with its image and its model; report the space freed (ADR-0033).

## Commands

```bash
scripts/check.sh                  # everything CI checks, on every supported Python
scripts/check.sh --containers     # plus image build and Compose smoke test

uv sync --all-extras              # install everything, including dev tools
uv run pytest                     # tests (SQLite, and PostgreSQL when the URL is set)
uv run pytest --cov               # with the 80% coverage gate
uv run ruff check .               # lint
uv run ruff format .              # format (also formats Python blocks in Markdown)
uv run mypy                       # strict type-check of src and tests
uv run lint-imports               # module boundary rules (ADR-0010)
uv run arbiter init               # local workspace: arbiter.yaml, SQLite database, .env
uv run arbiter keys create --name demo --role admin   # prints an API key once
uv run arbiter serve              # HTTP application on 127.0.0.1:8080, docs at /docs
uv run arbiter usage report       # usage and estimated cost; --locale it
uv run arbiter budgets list       # budgets create --limit 50 --hard; budgets delete ID
uv run arbiter audit verify       # recompute the audit chain
uv run arbiter pii detectors      # what PII detection validates and misses
uv run arbiter systems apply -f examples/systems.yaml   # declare and classify systems
uv run arbiter systems show KEY   # indicative tier, obligations, provisions, dates
uv run arbiter scan               # findings from inventory, classification and traffic
uv run arbiter systems discover   # candidate systems in the traffic; --draft for YAML
uv run arbiter demo run --all     # invented scenarios in the tenant "demo"; demo list
uv run arbiter findings list      # then: findings review ID --to confirmed --reviewer NAME
uv run arbiter digest run --locale it   # daily digest; --locale all --format both -o DIR
uv run arbiter report system KEY  # one system in full; report audit: the audit log
uv run arbiter ingest FILE --source litellm   # records of another gateway; default jsonl
uv run python scripts/measure_latency.py   # time the gateway adds to a request
uv run python scripts/check_legal_sources.py   # legal sources of the pack, by checksum
uv run alembic revision --autogenerate -m "..." --rev-id 000N   # new migration
```

An autogenerated migration must be tidied by hand before it is committed: portable types
(`sa.DateTime(timezone=True)`, `sa.BigInteger()` for amounts), plain `op.create_index`
instead of batch blocks, no marker comments. The schema test fails if models and
migrations differ.

`scripts/check.sh` must pass before a phase is closed.

## Working rules

- Work proceeds in phases 0–7. Stop at the end of each phase for approval.
- Every non-trivial choice: at least two options in a table (complexity, Azure cost,
  scalability, security, compliance/privacy, maintainability, lock-in), a recommendation,
  then wait for the decision. Record it as an ADR. Accepted ADRs are superseded, never
  edited.
- The owner sometimes answers with a filled-in template. A line left as a placeholder
  (for example `[confermato / modifiche]`) is not a decision: keep the item open and ask.
- Conversation with the owner is in Italian. Code, comments, docs, ADRs and commit
  messages are in English (ADR-0004).
- User-facing outputs (digest, reports, classifier text) exist in EN and IT.
- AI Act rules are written only from the official text. The EUR-Lex website refuses
  automated access, so the Official Journal documents are retrieved by CELEX number from
  the Publications Office (`https://publications.europa.eu/resource/celex/<CELEX>`), and
  the owner confirms the quoted articles on EUR-Lex (ADR-0034). A legal rule pack lists
  its sources with retrieval date and SHA-256, and carries `review: pending` until that
  confirmation; outputs say so. Repeat the check, with a search for corrigenda and later
  amending acts, at every release of the pack.
- Every user-facing output states that Arbiter is a support tool and not legal advice.
  Never write "compliant"; use "indicative" and "no findings".
- An LLM may suggest classification inputs, never decide a classification (ADR-0003).
- No Azure resources before Phase 6 (ADR-0008).
- Say what was verified and what was not. Never report something as tested if it only
  exists.
- Never write that the project is published, released or available on PyPI until the
  owner has published it. Install instructions with `pip` say "once published" and give
  the way from a clone.
- Publishing to PyPI or any other outward-facing action is prepared, then triggered by
  the owner.
- At the end of each phase: phase summary in `docs/phases/`, ADR index and open questions,
  `CHANGELOG.md`, and this file's "Resume here" section.
- When a phase is nearly done, list for the owner what is good and what is weak about
  where it stands and the possible improvements, and record them in the "Release
  improvement tracking" table of `README.md`. Update the status of earlier rows.

### Session rules (set by the owner on 2026-10-02)

- Commit and push to `main` without asking each time, with Conventional Commits. Ask
  for confirmation only for actions that cannot be undone or that reach outside the
  repository other than a push: publishing to PyPI, creating resources, changing
  repository settings.
- When bringing a decision, number the options. The owner answers by number, for example
  "1: accept, 2: option B".
- In the answer template suggested to the owner, write next to each number a short
  description of what it chooses, for example "D1: 2 (HMAC-SHA-256 with a pepper)", so
  that the answer can be read and found again later without the option tables.
- Never use the em-dash character (U+2014), anywhere: code, comments, documentation,
  commit messages, generated outputs and conversation. Use a colon, a comma, brackets or
  two sentences. `scripts/check.sh` and CI fail when a tracked file contains one.
- Every commit and push brings the whole `README.md` up to date, not only one section:
  the status at the top, "Where the project is" (phases, the steps in progress, the
  date), the capability tables, the commands, the limits, the roadmap and the tracking
  tables. Read it through before each commit and fix what the change made stale. Commit
  and push them together (asked again by the owner on 2026-10-02).
- When the owner asks for improvements and optimisations, make the ones that need no
  decision and declare each in the README table "Release improvement tracking", with
  what was measured or verified. Bring the ones that need a decision as option tables.
  When a weakness recorded for an earlier phase stops being true, say so in the column
  "What changed since" of the table "Where each phase stands"; the first two columns of
  a closed phase are kept as written.
- Before closing a working session, or when the owner writes "chiudiamo": follow the
  closing steps under "Codespaces hygiene".
- No automated test and no CI job may depend on a real model. A test that calls a real
  endpoint is opt-in and skipped by default; prompts sent to real models are synthetic
  (ADR-0033).
- When the owner writes "riprendi" in a new session, resume from this file without
  asking for context.

## Technical constraints (from the brief)

- Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, uv
- ruff, mypy strict, pytest with coverage > 80% on core
- Core never imports Azure SDKs; adapters implement `Protocol` ports
- No secrets in code; configuration through environment and files
- PII is redacted before persistence

## Architecture rules

- `core` imports nothing from `gateway`, `compliance`, `adapters`, `cli`, `migrations`.
- `gateway` and `compliance` never import each other; they share events and ports in `core`.
- Only `gateway.api` and `cli` import `adapters`. Only `adapters.azure` imports `azure.*`.
- Only `gateway.api` imports the web framework; `cli.serve` imports it lazily.
- The base install (no extras) must keep working: optional dependencies are imported
  inside the function that needs them and raise `MissingExtraError` when absent.
- The project must build, test and run with no container runtime (ADR-0025).
- One schema for SQLite and PostgreSQL: generic `JSON`, `Uuid`, `UTCDateTime`; no
  dialect-specific SQL in shared code. Every model change comes with a migration; a test
  compares the two.
- Every tenant-owned table has a non-nullable `tenant_id`.
- Events are published through the outbox in the caller's transaction; handlers are
  idempotent on the event id. Payloads carry identifiers, never content.
- A port is added to `core.ports` together with its first implementation, not before.
- Every automated outcome is a `Decision` written to the audit log (from Phase 3).
- Rules are YAML data with a closed operator set; no code in rule packs.
- No prompt or completion text is persisted unless a system opted in. Error messages
  from handlers and providers are not stored; only the exception class name is.
- The same holds for logs and error responses: a validation error names the field and
  never echoes the input, and a provider's own error message is dropped.
- Audit entries name things by identifier, never by name, and contain no floats: amounts
  are decimal strings (ADR-0029).
- No database transaction is open while a model provider is being called.
- Money is `Decimal` in code and the `DecimalAmount` column type in the schema; prices in
  configuration are strings, never YAML numbers (ADR-0030).
- `gateway.api` and `cli` are the composition roots: the only places where the gateway
  and the compliance toolkit meet. The gateway reaches the inventory only through the
  `SystemDirectory` port.
- A classification or a finding is a proposal until a person reviews it (ADR-0037). The
  engine's result is never altered; a review is a separate record. Outputs say
  "indicative" until then.
- A missing answer is never read as "no": classification rules are evaluated with three
  values (`evaluate_partial`), and the tier is `undetermined` while a more severe outcome
  is still possible (ADR-0035). Scan rules use two values: a control that is not declared
  counts as not attested.
- A rule over details of an area starts from the area fact, so that the details are not
  asked of systems outside the area.
- Reviewers appear in reviews and audit entries by principal id, never by name.
- Plugins are loaded by name through `PluginRegistry`, never imported by `core` or
  `gateway`; a provider or detector declares its own settings model (ADR-0011).
- Test fixtures that look like secrets (keys, tokens, private key blocks) are assembled
  from parts, or the secret scan in CI flags them. Run the gitleaks command of
  `ci.yml` locally before pushing such a change, and before pushing a new or changed
  rule pack: `.gitleaks.toml` allows `message_key:` lines and nothing else.
- CI cancels the run of a commit when a newer one is pushed. After a series of pushes,
  only the last run says anything: wait for it before calling a phase green.

## Code conventions

- `src` layout; absolute imports only; line length 100.
- Timestamps are timezone-aware UTC (`utcnow()`); naive datetimes are rejected.
- Primary keys come from `new_id()` (UUIDv7).
- Errors raised by Arbiter derive from `ArbiterError`; the CLI prints them as
  `Error: ...` and exits 1, without a traceback.
- Tests: one behaviour per test, named as a sentence. Database tests take the `database`
  fixture and run on both engines. CLI tests are synchronous. HTTP tests use
  `tests/api_support.py` and start with `pytest.importorskip("fastapi")`.
- User-facing text goes through `core.i18n` with a key in `locales/en.yaml` and
  `locales/it.yaml`; a test checks that both have the same keys and placeholders.
