---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0032: Make `0.1.0a1` the first release and skip `0.0.1`

## Context and Problem Statement

ADR-0005 planned a `0.0.1` release in Phase 2 whose only purpose was to take the name
`ai-arbiter` on PyPI. It was prepared and never published. At the end of Phase 3 the
package contains a working gateway, so the first publication can be a release with real
content, and publishing an older, nearly empty version first would add a step and a
version nobody should install.

## Considered Options

- **A.** Set the version to `0.1.0a1` and skip `0.0.1`. The first publication, whenever
  the owner triggers it, takes the name.
- **B.** Publish `0.0.1` from the Phase 2 commit first, then move to `0.1.0a1`.
- **C.** Keep `0.0.1` in `pyproject.toml` for now.

## Decision Outcome

Chosen option: **A**, decided by the project owner.

- `pyproject.toml` carries `0.1.0a1`. The development status classifier becomes Alpha.
- The name `ai-arbiter` stays unreserved until the owner publishes. Before publishing,
  check that <https://pypi.org/project/ai-arbiter/> still returns "not found".
- Publishing remains an action of the owner, through the release workflow
  (`docs/releasing.md`). Nothing publishes on its own.
- A pre-release is not installed by `pip install ai-arbiter` unless `--pre` is given or
  the version is named. That is intended for an alpha; install instructions say so until
  `0.1.0`.

This ADR replaces one sentence of ADR-0005: "In Phase 2 a `0.0.1` release is published
[...] to reserve the name." Everything else in ADR-0005 stands: the names, the trusted
publisher, the owner as the one who publishes.

### Consequences

- Good: the first thing on PyPI is something worth installing; PEP 541's concern about
  empty packages does not arise.
- Good: one release step fewer.
- Bad: the name can be taken by someone else until the first publication. If that
  happens, ADR-0005 has to be revisited.
- Bad: the release workflow stays unexercised until then (improvement I-06).

## Pros and Cons of the Options

| Criterion | A. First release is `0.1.0a1` | B. `0.0.1` first | C. Stay on `0.0.1` |
|---|---|---|---|
| Complexity | Lowest | A tag on an old commit, then a second release | None now, the question returns |
| Azure cost | None | None | None |
| Scalability | Not affected | Not affected | Not affected |
| Security | Name unreserved until publication | Name reserved at once | Name unreserved, version misleading |
| Compliance / privacy | Not affected | Not affected | Not affected |
| Maintainability | One version line | A version that must never be used | Version says less than the code does |
| Lock-in | None | None | None |

## More Information

- [ADR-0005](0005-naming-and-distribution.md)
- [Releasing](../releasing.md)
