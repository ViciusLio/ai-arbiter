---
status: proposed
date: 2026-10-02
decision-makers: Project owner
---

# 0024 — Development tooling baseline

> Status note: these choices were applied in Phase 2 before acceptance, because the
> project owner asked to proceed with scaffolding and each of them can be reversed in
> minutes without touching application code. Rejecting a line means changing that line.

## Context and Problem Statement

The brief fixes uv, ruff, mypy strict, pytest and GitHub Actions. Scaffolding needs a few
more tools that the brief leaves open. None of them shapes the architecture, so they are
recorded together instead of one ADR each.

## Decision Outcome

| Concern | Choice | Alternatives considered | Reason |
|---|---|---|---|
| Build backend | hatchling | `uv_build`, setuptools | Mature, tool-agnostic: the package builds without uv installed |
| Version source | Static in `pyproject.toml`, read at runtime from package metadata | `hatch-vcs` (from git tags) | One place to read; the release workflow fails if the tag and the version differ |
| CLI framework | Typer | Click, argparse | Typed signatures, generated help; already named in the architecture |
| Async tests | pytest-asyncio, auto mode | anyio plugin | Only asyncio is targeted |
| Import boundaries | import-linter | Custom AST test | Required by ADR-0010; declarative contracts |
| Time-ordered UUIDs | Small in-house UUIDv7 (RFC 9562) | `uuid-utils`, `uuid6` packages | `uuid.uuid7` exists only from Python 3.14; fifteen lines avoid a dependency |
| Dependency audit | pip-audit on the locked set | Safety, OSV-Scanner | PyPA tool, no account needed |
| Secret scanning | gitleaks in CI, plus GitHub secret scanning on the repository | TruffleHog | Runs offline on the checkout; no token |
| Static security analysis | CodeQL and ruff's `S` rules | Bandit as a separate tool | First-party action; `S` is the Bandit rule set |
| Workflow actions | Pinned to commit SHAs, updated by Dependabot | Version tags | A moved tag cannot change what CI runs |
| Container base | `python:3.12-slim`, non-root user | Distroless, Alpine | Small enough, no musl wheel issues, debuggable |
| Container image scan | Deferred to Phase 6 hardening | Trivy, Grype in CI now | One more third-party action for an image that is not deployed yet |
| Local Python | `.python-version` = 3.12 (lowest supported) | Latest | Catches use of newer syntax and stdlib early |
| CI matrix | Linux on 3.12, 3.13, 3.14; Windows on 3.12; PostgreSQL job on Linux | Full cross-product | Covers both operating systems and both databases without tripling CI time |
| Pre-commit hooks | Not included | pre-commit | CI runs the same checks; hooks can be added on request |

### Consequences

- Good: every tool beyond the brief is listed in one place with what it replaced.
- Bad: several decisions share one record; if one is contested it is split into its own
  ADR.

## More Information

- [Phase 2 summary](../phases/phase-2-scaffolding.md)
