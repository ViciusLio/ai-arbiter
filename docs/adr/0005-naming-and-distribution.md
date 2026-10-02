---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0005 — Name the distribution `ai-arbiter`, keep the brand "Arbiter"

## Context and Problem Statement

`arbiter` on PyPI is taken (a data-handling library, last released in 2021). Several
GitHub projects in the LLM space are also called Arbiter, including an LLM router and an
evaluation framework published on PyPI as `arbiter-ai`.

## Considered Options

- **A.** Keep the brand "Arbiter" and publish under a different distribution name.
- **B.** Pick a new, unique name.

## Decision Outcome

Chosen option: **A**, with the names fixed by the project owner:

| Thing | Name |
|---|---|
| Brand | Arbiter |
| Repository | `ai-arbiter` |
| PyPI distribution | `ai-arbiter` |
| Import package | `ai_arbiter` |
| CLI command | `arbiter`, with alias `ai-arbiter` |

Checked on 2026-10-02 against the PyPI JSON API: `ai-arbiter` returns 404 (free);
`arbiter-ai` exists (0.2.0, "Native PydanticAI evaluation with automatic cost tracking");
`arbiter` exists (1.1.2, 2021).

In Phase 2 a `0.0.1` release is published through GitHub Actions with PyPI Trusted
Publishing to reserve the name.

### Consequences

- Good: `uvx ai-arbiter` works because the alias matches the distribution name.
- Bad: `arbiter-ai` and `ai-arbiter` differ only by word order. The README and docs state
  near the top that the projects are unrelated, and install instructions always spell the
  full name.
- Bad: the `arbiter` command can collide with another tool on a user's PATH; the
  `ai-arbiter` alias is the documented fallback.
- Risk: PyPI treats an empty placeholder as name squatting (PEP 541, "a package has no
  functionality or is empty") and may remove it. The `0.0.1` release must therefore do
  something real, however small: an importable package, a working `arbiter --version`,
  a README and a repository link.
- Follow-up: publishing is an outward-facing action. The workflow is prepared in Phase 2;
  the project owner configures the trusted publisher on PyPI and triggers the release.

## Pros and Cons of the Options

| Criterion | A. Brand + other distribution name | B. New unique name |
|---|---|---|
| Discoverability | Shared with other "Arbiter" projects | Best |
| Install/command symmetry | Needs an alias | Natural |
| Effort | None | A name must be found and checked |

## More Information

- [Phase 0 analysis](../phases/phase-0-analysis.md), section 8 (D4)
- [PEP 541](https://peps.python.org/pep-0541/)
- [arbiter-ai on PyPI](https://pypi.org/project/arbiter-ai/)
