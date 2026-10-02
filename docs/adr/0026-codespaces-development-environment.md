---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0026 — Develop in GitHub Codespaces with a dev container

## Context and Problem Statement

The project owner's computer is a corporate machine on which neither Docker nor uv will
be used. Phase 2 was built there with what was available, and its summary lists what
could not be verified as a result: the Dockerfile, the Compose stack, every test on
PostgreSQL, Python 3.12. From Phase 3 onwards the gateway makes those gaps more costly:
PostgreSQL is its production database and row locking, on which the audit chain relies
(ADR-0017), does not exist on SQLite.

## Considered Options

- **A.** GitHub Codespaces with a dev container checked into the repository: Python 3.12,
  3.13 and 3.14, uv, Docker-in-Docker and PostgreSQL.
- **B.** Keep developing on the corporate machine and rely on CI for everything it cannot
  run (ADR-0025 as written).
- **C.** A personal machine or a self-managed cloud VM with the tools installed by hand.

## Decision Outcome

Chosen option: **A**, decided by the project owner. Development moves to Codespaces
starting with Phase 3.

The dev container (`.devcontainer/`):

| Need | How |
|---|---|
| Python 3.12, 3.13, 3.14 | Installed by uv when the container is created; 3.12 is the default (`.python-version`) |
| uv | Copied from the official uv image into the dev container image |
| Docker | Docker-in-Docker feature: the project image and the project Compose stack are built and run inside the dev container |
| PostgreSQL | A sidecar service of the dev container, reachable as host `postgres`; `ARBITER_TEST_DATABASE_URL` is preset, so `uv run pytest` runs every database test on both engines |
| Tooling | GitHub CLI, Claude Code, editor extensions for Python, ruff, mypy, TOML, YAML, Docker and Mermaid |

Consequences for earlier decisions:

- ADR-0025 is extended, not withdrawn. Running without containers stays a supported and
  tested path: it is the quickstart and the offline CLI. Containers are now verified in
  Codespaces as well as in CI.
- ADR-0008 is unaffected: Codespaces is a development environment, not an Azure resource
  of the project.

### Consequences

- Good: the gaps listed in the Phase 2 summary can be closed before Phase 3 starts.
- Good: a contributor gets a working environment with one click; the setup is code,
  reviewed and versioned.
- Good: nothing is installed on the corporate machine.
- Bad: Codespaces consumes the account's included hours and storage; beyond the free
  allowance it is billed. Stopping the codespace when idle matters.
- Bad: Docker-in-Docker needs a privileged container. That is acceptable in a disposable
  development environment and is not used anywhere else.
- Bad: the dev container configuration was written on a machine that cannot run it. It
  is unverified until the first codespace is created; expect to fix it then.
- Follow-up: the first task in Codespaces is to run the verification checklist in
  `CLAUDE.md` and to update the "not verified" table of the Phase 2 summary.

## Pros and Cons of the Options

| Criterion | A. Codespaces dev container | B. Corporate machine + CI | C. Personal machine or VM |
|---|---|---|---|
| Complexity | Low: configuration in the repository | Lowest | Medium: manual setup, not reproducible |
| Azure cost | None (GitHub billing, free allowance first) | None | None, or the cost of a VM |
| Scalability | Machine size chosen per codespace | Fixed | Fixed |
| Security | Isolated, disposable; no project tooling on the corporate machine | Constrained by corporate policy | Depends on the machine |
| Compliance / privacy | Code and test data live in the owner's GitHub account | Personal project on a corporate device | Under the owner's control |
| Maintainability | Environment defined as code; Dependabot updates it | Feedback on containers and PostgreSQL only after a push | Drifts over time |
| Lock-in | Dev Container specification is open; works with any compatible tool | None | None |
| Fidelity to production | PostgreSQL and containers available while developing | SQLite only while developing | Depends |

## More Information

- [ADR-0025](0025-docker-free-local-development.md)
- [Phase 2 summary](../phases/phase-2-scaffolding.md), section "Not verified"
- [Development Containers specification](https://containers.dev/)
