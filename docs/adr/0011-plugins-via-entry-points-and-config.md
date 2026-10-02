---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0011: Discover plugins through entry points, activate them only from configuration

## Context and Problem Statement

The brief asks for a plugin architecture where every capability has an explicit interface
and can be replaced or disabled from configuration, with Azure as one implementation among
others. A mechanism is needed to find implementations and choose among them.

## Considered Options

- **A.** Interfaces as `typing.Protocol` in `core.ports`; implementations registered as
  Python entry points; configuration names which ones are active.
- **B.** Configuration holds dotted import paths (`"ai_arbiter.adapters.azure:KeyVault"`).
- **C.** A hook framework (pluggy).

## Decision Outcome

Chosen option: **A**.

- One entry-point group per port, for example `ai_arbiter.llm_providers`,
  `ai_arbiter.secret_stores`, `ai_arbiter.pii_detectors`, `ai_arbiter.telemetry_sources`,
  `ai_arbiter.notifiers`, `ai_arbiter.local_collectors`.
- Built-in adapters are registered the same way as third-party ones.
- **Nothing is activated by being installed.** A plugin runs only if the configuration
  names it. Unknown names fail at startup.
- Each plugin declares a Pydantic settings model; its configuration is validated at
  startup, before the first request.

### Consequences

- Good: third parties can add a provider or detector without touching the repository.
- Good: the allowlist prevents an unrelated installed package from injecting code.
- Bad: entry points are resolved at install time; in development the package must be
  installed in editable mode.

## Pros and Cons of the Options

| Criterion | A. Entry points + config | B. Dotted paths in config | C. pluggy |
|---|---|---|---|
| Complexity | Low | Lowest | Medium (hook specs, call ordering) |
| Azure cost | None | None | None |
| Scalability | Resolved once at startup | Same | Same |
| Security | Explicit allowlist of named plugins | Config can import arbitrary modules | Any installed plugin registers hooks unless filtered |
| Compliance / privacy | Active plugins are listable and auditable | Same | Harder to enumerate |
| Maintainability | Standard packaging mechanism | Paths break on refactor | Extra dependency and concepts |
| Lock-in | None | None | On pluggy |

## More Information

- [Interfaces](../architecture/interfaces.md)
