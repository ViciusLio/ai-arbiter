# CLAUDE.md — Arbiter

AI Governance Gateway & EU AI Act Compliance Toolkit. Open source, Apache 2.0.
Repository: <https://github.com/ViciusLio/ai-arbiter>

This file is the hand-over between sessions. A session in a new environment has no
memory of earlier ones: everything needed to resume is here or linked from here.

## Resume here

**State on 2026-10-02.** Phases 0, 1 and 2 are done and verified. Phase 3 is open: the
owner gave the go-ahead, and **no Phase 3 code is written until the owner answers the
questions in Step 2**. They were presented on 2026-10-02; if the answers are not in this
file, present them again.

### Step 1 — Environment: verified

Verified in Codespaces on 2026-10-02, at commit `c8ccce3`:

- The dev container has uv, Python 3.12, 3.13 and 3.14, Docker and the PostgreSQL sidecar.
- `scripts/check.sh --containers` passes to the end with no change needed: lint, types,
  import rules; 121 tests on each of Python 3.12, 3.13 and 3.14, the database tests on
  SQLite and PostgreSQL; 98% coverage; 90 tests without extras; image build, non-root
  user, Compose stack healthy, `/healthz` and `/readyz`.
- CI on GitHub is green at the same commit, CodeQL included.

Not verified: the release workflow (it runs on the `0.0.1` tag, which the owner pushes),
and the CodeQL alert list (not readable with the Codespaces token; the owner checks the
Security tab). Details in `docs/phases/phase-2-scaffolding.md`.

In a new codespace, repeat the quick check before working: `git config user.email`,
`pg_isready -h postgres -U arbiter -d arbiter_test`, `scripts/check.sh`.

### Step 2 — Decisions waiting for the owner

| # | Decision | Needed by |
|---|---|---|
| 1 | Q1: confirm the split of v0.1 between core and deferrable components (ADR-0009). PII detection is the heaviest core item | Phase 3 code |
| 2 | The four opening decisions of Phase 3 (Step 3), each presented with numbered options | Phase 3 code |
| 3 | Publish `0.0.1` to reserve the name on PyPI (`docs/releasing.md`) | Before `0.1.0-alpha` |
| 4 | Azure subscription and monthly budget (ADR-0008) | Phase 6 |

After the answers: record one ADR per decision, update the ADR index and `CHANGELOG.md`,
then implement the core of Phase 3 in the order of Step 4. Stop at the end of the phase.

The v0.1 scope is accepted (ADR-0009). It has a **core** that `0.1.0` cannot ship without
and **deferrable** components that may follow in v0.1.x. Plan Phases 3 and 4 core first;
start a deferrable item only when the core of that phase is done.

### Step 3 — Phase 3: four decisions to bring first

Presented to the owner on 2026-10-02, each as an option table with the seven criteria and
a recommendation; answers pending. The options below are a summary, not decisions.
Recommended: 1 — HMAC-SHA-256 with a pepper; 2 — in-house canonicaliser without floats;
3 — versioned YAML file; 4 — unknown and unpriced, with an opt-in flagged estimate.

1. **API key format and hashing.** Options: random high-entropy token with a recognisable
   prefix and a key id, stored as a plain SHA-256 digest; the same with HMAC-SHA-256 and
   a server-side pepper from the secret store; a slow password hash (argon2); signed
   stateless tokens. Points to weigh: per-request latency, what a database leak exposes,
   revocation, secret-scanner friendliness of the prefix.
2. **Canonical JSON for the audit hash (ADR-0017).** Options: a dependency implementing
   RFC 8785; an in-house canonicaliser limited to the types audit entries use (no
   floats), tested against the RFC vectors; `json.dumps(sort_keys=True)`, which is not
   RFC-conformant. Points to weigh: third parties must be able to re-verify an export
   with other tools.
3. **Price catalogue format and currency.** Options: a versioned YAML data file shipped
   like a rule pack, with overrides in configuration; a database table managed through
   the API; importing a third-party price list. Points to weigh: `Decimal` arithmetic,
   price per million tokens, cached-token and regional prices, one reporting currency
   per tenant with an explicit conversion rate, the catalogue version stored on every
   interaction.
4. **Token counts when a provider returns no usage.** Options: leave them unknown and
   report the interaction as unpriced; a character-based estimate flagged as estimated; a
   tokenizer dependency per model family. Points to weigh: budgets enforced on estimates,
   honesty of FinOps reports, dependency weight in the request path.

Also deferred to Phase 3: anchoring sink details for the audit chain (ADR-0017).

### Step 4 — Phase 3 task list (gateway MVP)

Core (ADR-0009), in this order:

1. Identity: teams, projects, principals, API keys, three roles.
2. Rule engine (`core.rules`): rule pack schema, condition evaluator, match trace.
3. Audit: hash chain, verification, export (ADR-0017, ADR-0023).
4. Providers: mock, OpenAI-compatible, Azure OpenAI; plugin settings models (ADR-0013).
5. Router: candidates, priority and cost strategies, fallback and retry.
6. FinOps: versioned price catalogue, metering, roll-ups, budgets.
7. Redaction: built-in detectors with EU and Italian formats (ADR-0014).
8. Policy: fact collection, pre-call evaluation, default policy pack.
9. HTTP: `/v1/chat/completions` with streaming, `/v1/models`, admin endpoints.
10. Request-path latency measured against the mock provider.

Deferrable to v0.1.x, only after the core above: routing constraints by risk class,
post-call policy evaluation, external anchoring of the audit head, opt-in store of
redacted content.

Target release at the end of Phase 3: `0.1.0-alpha`.

## Names (ADR-0005)

| Thing | Name |
|---|---|
| Brand | Arbiter |
| Repository, PyPI distribution | `ai-arbiter` |
| Import package | `ai_arbiter` |
| CLI | `arbiter`, alias `ai-arbiter` |
| Author | ViciusLio |

Unrelated to `arbiter-ai` on PyPI. Always write the full distribution name in install
instructions. Version in `pyproject.toml`: `0.0.1`, the name-reserving release, not
published yet; the owner publishes it (`docs/releasing.md`).

## Git

- Commits are authored as **ViciusLio <viciuslios@gmail.com>**, always. Check
  `git config user.email` before the first commit in a new clone or codespace; if it
  differs, set it in the repository's local config, never globally.
- Conventional Commits. End commit messages with the co-author trailer of the assistant
  that wrote them.
- Work on `main` until the owner asks for branches. Never force-push `main`.

## Reference documents

- `docs/PROJECT_BRIEF.md` — initial requirements, in Italian. Never edited; changes go
  through ADRs.
- `docs/phases/phase-N-*.md` — analysis and summary of each phase
- `docs/architecture/` — overview, flows, data model, interfaces
- `docs/adr/` — decisions (MADR); index and open questions in `docs/adr/README.md`
- `docs/releasing.md` — how a release is published
- `CHANGELOG.md` — Keep a Changelog + SemVer, entries linked to ADRs

## Environment (ADR-0026)

Development happens in the dev container (`.devcontainer/`), in GitHub Codespaces.

- Python 3.12, 3.13, 3.14 installed by uv; 3.12 is the default (`.python-version`).
- Docker-in-Docker: the project image and `deploy/compose/compose.yaml` run inside it.
- PostgreSQL is the sidecar service `postgres`; `ARBITER_TEST_DATABASE_URL` is preset, so
  database tests run on SQLite and PostgreSQL.
- The project Compose stack publishes its own PostgreSQL on `127.0.0.1:5432` of the dev
  container; the test database is on host `postgres`. They do not collide.
- Stop the codespace when idle; it is billed beyond the free allowance.

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
uv run arbiter init               # local workspace: arbiter.yaml + SQLite database
uv run arbiter serve              # HTTP application on 127.0.0.1:8080
uv run alembic revision --autogenerate -m "..."   # new migration
```

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
- AI Act rules are written only from the official EU sources on EUR-Lex
  (<https://eur-lex.europa.eu/>). Before Phase 4, verify the current text and the status
  of any pending change to the application calendar, and record the verification date in
  the rule pack. Dates in the Phase 0 analysis come from secondary sources.
- Every user-facing output states that Arbiter is a support tool and not legal advice.
  Never write "compliant"; use "indicative" and "no findings".
- An LLM may suggest classification inputs, never decide a classification (ADR-0003).
- No Azure resources before Phase 6 (ADR-0008).
- Say what was verified and what was not. Never report something as tested if it only
  exists.
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
- Before closing a working session, or when the owner writes "chiudiamo": update the
  "Resume here" section with state, open decisions and next steps, commit, push, and
  remind the owner to stop the codespace.
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

## Code conventions

- `src` layout; absolute imports only; line length 100.
- Timestamps are timezone-aware UTC (`utcnow()`); naive datetimes are rejected.
- Primary keys come from `new_id()` (UUIDv7).
- Errors raised by Arbiter derive from `ArbiterError`; the CLI prints them as
  `Error: ...` and exits 1, without a traceback.
- Tests: one behaviour per test, named as a sentence. Database tests take the `database`
  fixture and run on both engines. CLI tests are synchronous.
