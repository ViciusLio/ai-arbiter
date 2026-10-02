---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0025 — Develop locally without Docker; build and test containers in CI only

> Status note: the constraint comes from the project owner (Docker cannot be installed or
> used on the corporate development machine). The adaptation was applied in Phase 2 ahead
> of acceptance and accepted on 2026-10-02.
>
> Extended by [ADR-0026](0026-codespaces-development-environment.md), decided the same
> day: development moves to GitHub Codespaces, where Docker and PostgreSQL are available.
> What this ADR establishes still holds: the project must build, test and run with no
> container runtime, and CI verifies the container deliverables. The statement that CI is
> the *only* place where containers run is replaced by ADR-0026.

## Context and Problem Statement

The brief asks for Docker Compose for local development, with emulators and mocks in
place of Azure services, and targets Azure Container Apps, which needs a container
image. Docker is not available on the project owner's machine and cannot be installed.
Local development must therefore work with no container runtime, while the image and the
Compose file still have to exist and be known to work.

## Considered Options

- **A.** Docker-free local development as the primary path; Dockerfile and Compose file
  stay in the repository and are built and smoke-tested in CI.
- **B.** Drop the Compose file; keep only the Dockerfile for deployment.
- **C.** Require an alternative container runtime locally (Podman, WSL2 with a Linux
  Docker engine).

## Decision Outcome

Chosen option: **A**.

Local development, no containers:

| Need | Local substitute |
|---|---|
| Database | SQLite file (ADR-0015); PostgreSQL only if one is reachable through `ARBITER_TEST_DATABASE_URL` |
| Model provider | In-process mock adapter (ADR-0013) |
| Event broker | In-process bus with outbox (ADR-0016) |
| Secrets | Environment secret store |
| Email | File-based notifier that writes messages to a local directory (Phase 4) |
| Running the app | `uv run arbiter serve` |

Containers, in CI only:

- The image is built on every push.
- A CI job starts the Compose stack (application, PostgreSQL, Mailpit), waits for
  readiness and calls the health endpoints. This is the only place the Compose file runs
  until someone with Docker uses it.
- The PostgreSQL integration suite runs in CI against a service container.
- In Phase 6 the image for Azure is built in CI or by Azure Container Registry, never on
  the development machine.

### Consequences

- Good: the five-minute quickstart needs only Python and uv, which widens the audience.
- Good: forces the offline-first path (ADR-0010) to be the well-trodden one.
- Bad: PostgreSQL-specific and container-specific failures are seen only after a push.
  The feedback loop for those is a CI run, not a local command.
- Bad: the Dockerfile and Compose file in this repository are unverified until the first
  CI run; the Phase 2 summary says so.
- Follow-up: the README quickstart leads with the Docker-free path and offers Compose as
  the alternative.

## Pros and Cons of the Options

| Criterion | A. Docker-free locally, containers in CI | B. No Compose | C. Alternative runtime |
|---|---|---|---|
| Complexity | Low | Lowest | Medium (setup outside the project's control) |
| Azure cost | None | None | None |
| Scalability | Not affected | Not affected | Not affected |
| Security | No local daemon needed | Same | Depends on the runtime and on company policy |
| Compliance / privacy | Local data stays in a SQLite file | Same | Same |
| Maintainability | Compose kept working by a CI smoke test | Brief requirement dropped | Extra local tooling to maintain |
| Lock-in | None | None | None |
| Fidelity to production | PostgreSQL exercised in CI only | Same | Highest locally |

## More Information

- Deviates from the brief ("Docker Compose per sviluppo locale"): Compose is kept, but it
  is no longer the primary local path.
- [ADR-0008](0008-local-only-until-phase-6.md), [ADR-0015](0015-postgres-and-sqlite-row-level-tenancy.md)
