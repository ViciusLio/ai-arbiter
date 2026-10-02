---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0010 — Ship one distribution with extras and enforce module boundaries by tooling

## Context and Problem Statement

The CLI must install quickly and run offline without pulling FastAPI or Azure SDKs, while
the gateway needs both. ADR-0005 fixes a single PyPI name, `ai-arbiter`, and a single
import package, `ai_arbiter`. The Phase 0 orientation was a multi-package uv workspace;
that is revisited here in the light of ADR-0005.

## Considered Options

- **A.** One distribution, `ai-arbiter`, with optional extras (`gateway`, `azure`, `pii`,
  `otel`, `all`). Module boundaries enforced by import-linter contracts in CI.
- **B.** uv workspace with several distributions (`ai-arbiter-core`, `-gateway`,
  `-compliance`, `-cli`) and `ai-arbiter` as a meta-package.
- **C.** One distribution with every dependency mandatory.

## Decision Outcome

Chosen option: **A**. This changes the Phase 0 orientation.

- `pip install ai-arbiter` gives core + compliance toolkit + CLI, with SQLite. No web
  framework, no cloud SDK.
- `pip install "ai-arbiter[gateway]"` adds FastAPI, the ASGI server, the HTTP client and
  the PostgreSQL driver.
- `pip install "ai-arbiter[azure]"` adds the Azure adapters.
- Import rules checked in CI (see [architecture overview](../architecture/README.md)):
  `core` imports no other Arbiter package; `gateway` and `compliance` never import each
  other; only `adapters.azure` imports `azure.*`; only composition roots import `adapters`.
- Code that needs an extra fails with a message naming the extra to install.

### Consequences

- Good: one name to reserve, one version, one release pipeline.
- Good: the boundary a workspace would give is kept, as a checked rule.
- Bad: boundaries are enforced by a linter, not by packaging; a contributor can break
  them locally and only CI will object.
- Bad: optional imports need guarding and a test job that installs the base package alone.

## Pros and Cons of the Options

| Criterion | A. One distribution + extras | B. Workspace, many distributions | C. One distribution, all mandatory |
|---|---|---|---|
| Complexity | Low | High (inter-package versions, several PyPI names) | Lowest |
| Azure cost | None | None | None |
| Scalability | Same runtime | Same runtime | Same runtime |
| Security | Base install has a small dependency surface | Smallest per package | Every user gets every dependency |
| Compliance / privacy | Offline CLI has no network-capable server stack | Same | Azure SDKs on every laptop |
| Maintainability | One release, linter-enforced boundaries | Coordinated releases | Simple, but boundaries erode |
| Lock-in | None | None | None |

## More Information

- Supersedes the "workspace" orientation in the Phase 0 analysis, section 9.
- [ADR-0005](0005-naming-and-distribution.md)
