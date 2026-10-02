---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0020: Build a modular monolith: one image, started in different roles

## Context and Problem Statement

The system has a latency-sensitive data plane (the LLM proxy), a control plane (admin and
compliance API), background work (outbox dispatch, scans) and scheduled jobs (digest).
They scale differently, but one person maintains all of them and the CLI must run the
same logic with no server.

## Considered Options

- **A.** Modular monolith: one codebase and one container image; the process is started
  with a set of roles (`gateway`, `admin`, `worker`), and jobs are CLI commands.
- **B.** Separate services per module from the start.
- **C.** Single process, no role separation.

## Decision Outcome

Chosen option: **A**.

- `arbiter serve --roles gateway,admin` starts the HTTP application with the selected
  routers. `arbiter worker` runs the outbox dispatcher and event handlers.
  `arbiter digest run` and `arbiter scan` are one-shot jobs.
- Local development and the demo run every role in one process.
- On Azure Container Apps the same image runs as two apps (gateway; admin + worker) and
  one scheduled job (digest), each with its own scaling rule.
- Business logic lives in application services that are called by both the HTTP routers
  and the CLI. Routers and commands stay thin.

### Consequences

- Good: one build, one version, one deployment artefact; the split is a deployment choice.
- Good: the standalone CLI calls the same services directly against SQLite.
- Bad: all roles share a dependency set and a release cadence.
- Bad: the module boundaries are logical; they rely on ADR-0010's import rules.

## Pros and Cons of the Options

| Criterion | A. Modular monolith with roles | B. Microservices | C. Single undivided process |
|---|---|---|---|
| Complexity | Low to medium | High | Lowest |
| Azure cost | Two small apps and a job, scale to zero | One app per service | One app |
| Scalability | Data plane scales independently of the rest | Finest-grained | Everything scales together |
| Security | Gateway replicas need no admin routes mounted | Smallest blast radius per service | Admin API exposed wherever the proxy is |
| Compliance / privacy | Single audit path | Audit must be consistent across services | Single audit path |
| Maintainability | One repository, one pipeline | Many pipelines and contracts | Simple, but hard to split later |
| Lock-in | None | None | None |

## More Information

- [Architecture overview](../architecture/README.md), section "Runtime topology"
