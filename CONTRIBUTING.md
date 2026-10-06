# Contributing

Thank you for looking. Arbiter is a young project with one maintainer; issues, questions
and pull requests are welcome.

## Before you write code

Open an issue first for anything larger than a fix. Choices that shape the project are
written as decision records in [`docs/adr`](docs/adr/README.md), with the options that
were set aside: a change that reverses one needs a new record, not an edit.

## Setting up

The quickest way is the dev container in `.devcontainer/` (GitHub Codespaces or any Dev
Container tool). Without it you need Python 3.12 or newer and
[uv](https://docs.astral.sh/uv/):

```bash
uv sync --all-extras
uv run pytest
```

`scripts/check.sh` runs everything CI runs.

## What a change needs

- Tests: one behaviour per test, named as a sentence. Database tests run on SQLite and
  PostgreSQL.
- `uv run ruff check .`, `uv run ruff format .`, `uv run mypy` and `uv run lint-imports`
  pass. The last one enforces the module boundaries.
- Text that people read goes through the catalogues in `src/ai_arbiter/locales`, in
  English and Italian.
- No prompt, completion, tool argument or result is stored or logged.
- No real model, key or personal data in tests or examples: use invented data.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/).
- Say what you verified and what you did not.

## Rules about the law

A rule of the AI Act pack is written only from the official text, cites its provision,
and never claims that a system complies. If you have legal training and would review
the pack, that is the most valuable contribution this project can receive:
[ADR-0041](docs/adr/0041-legal-review-before-0-1-0.md).

## Licence

By contributing you agree that your contribution is licensed under Apache-2.0.
