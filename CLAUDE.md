# CLAUDE.md — Arbiter

AI Governance Gateway & EU AI Act Compliance Toolkit. Open source, Apache 2.0.

## Status

- **Current phase**: 2 — Scaffolding, awaiting approval
- **Next step**: owner decides ADR-0024, ADR-0025 and confirms ADR-0009; then Phase 3
  (gateway MVP). Open questions are in `docs/adr/README.md`.
- Version in `pyproject.toml`: `0.0.1` (name-reserving release, not published yet).

## Names (ADR-0005)

| Thing | Name |
|---|---|
| Brand | Arbiter |
| Repository, PyPI distribution | `ai-arbiter` |
| Import package | `ai_arbiter` |
| CLI | `arbiter`, alias `ai-arbiter` |

Unrelated to `arbiter-ai` on PyPI. Always write the full distribution name in install
instructions.

## Reference documents

- `docs/PROJECT_BRIEF.md` — initial requirements, in Italian. Never edited; changes go
  through ADRs.
- `docs/phases/phase-N-*.md` — analysis and summary of each phase
- `docs/architecture/` — overview, flows, data model, interfaces
- `docs/adr/` — decisions (MADR); index and open questions in `docs/adr/README.md`
- `docs/releasing.md` — how a release is published
- `CHANGELOG.md` — Keep a Changelog + SemVer, entries linked to ADRs

## Commands

```bash
uv sync --all-extras              # install everything, including dev tools
uv run pytest                     # tests (SQLite)
uv run pytest --cov               # with the 80% coverage gate
uv run ruff check .               # lint
uv run ruff format .              # format (also formats Python blocks in Markdown)
uv run mypy                       # strict type-check of src and tests
uv run lint-imports               # module boundary rules (ADR-0010)
uv run arbiter init               # local workspace: arbiter.yaml + SQLite database
uv run arbiter serve              # HTTP application on 127.0.0.1:8080
uv run alembic revision --autogenerate -m "..."   # new migration
```

- All five checks (pytest, ruff check, ruff format --check, mypy, lint-imports) must pass
  before a phase is closed.
- PostgreSQL tests run when `ARBITER_TEST_DATABASE_URL` points to an empty database;
  otherwise they are skipped. CI runs them.
- Behind a TLS-intercepting proxy, add `--system-certs` to `uv sync` and `uv build`.
- `.python-version` is 3.12, the lowest supported version. If only a newer interpreter is
  installed, pass `--python 3.13` (or set `UV_PYTHON`).

## Working rules

- Work proceeds in phases 0–7. Stop at the end of each phase for approval.
- Every non-trivial choice: at least two options in a table (complexity, Azure cost,
  scalability, security, compliance/privacy, maintainability, lock-in), a recommendation,
  then wait for the decision. Record it as an ADR. Accepted ADRs are superseded, never
  edited.
- Conventional Commits.
- Conversation with the owner is in Italian. Code, comments, docs, ADRs and commit
  messages are in English (ADR-0004).
- User-facing outputs (digest, reports, classifier text) exist in EN and IT.
- AI Act rules are written only from the official EU sources on EUR-Lex
  (<https://eur-lex.europa.eu/>). Before Phase 4, verify the current text and the status
  of any pending change to the application calendar, and record the verification date in
  the rule pack.
- Every user-facing output states that Arbiter is a support tool and not legal advice.
  Never write "compliant"; use "indicative" and "no findings".
- An LLM may suggest classification inputs, never decide a classification (ADR-0003).
- No Azure resources before Phase 6 (ADR-0008).
- Docker is not available on the development machine (ADR-0025). Local development uses
  SQLite and in-process substitutes; the Dockerfile and Compose file are verified by CI.
  Never claim they were tested locally.
- Publishing to PyPI or any other outward-facing action is prepared, then triggered by
  the owner.

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
