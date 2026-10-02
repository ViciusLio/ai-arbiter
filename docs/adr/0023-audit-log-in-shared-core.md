---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0023: Place the audit log in the shared core

## Context and Problem Statement

The project brief lists `audit` among the gateway modules. The brief also requires every
automated decision to be traced in the audit log. Classifications and findings are
automated decisions, and they are produced by the compliance toolkit, including when it
runs as a standalone offline CLI with no gateway installed. Under
[ADR-0010](0010-single-distribution-with-enforced-boundaries.md) the compliance package
cannot import the gateway package.

## Considered Options

- **A.** Audit lives in `ai_arbiter.core.audit`; the gateway exposes it over HTTP and the
  CLI exposes it as commands.
- **B.** Audit stays in `ai_arbiter.gateway.audit`, as in the brief; compliance decisions
  are audited only when the gateway is present.
- **C.** Two audit implementations, one per package.

## Decision Outcome

Chosen option: **A**. This is a deviation from the module list in the brief, approved by
the project owner.

- The `AuditLog` port, the hash chain, verification and export are in `core.audit`.
- `gateway.api` mounts the audit endpoints; `cli` provides `arbiter audit verify|export`.
- The user-facing description of the product still presents audit as a gateway
  capability; the placement is an internal matter.

### Consequences

- Good: one audit trail for policy, routing, budget, classification and finding
  decisions, with or without the gateway.
- Good: the standalone CLI produces a verifiable record of what it decided.
- Bad: `core` grows; it must stay free of HTTP and cloud dependencies, which the import
  rules enforce.

## Pros and Cons of the Options

| Criterion | A. In core | B. In gateway | C. Two implementations |
|---|---|---|---|
| Complexity | Low | Low | High |
| Azure cost | None | None | None |
| Scalability | Same | Same | Same |
| Security | One implementation to review | One implementation | Two chains to keep consistent |
| Compliance / privacy | Every automated decision is audited | Offline decisions are not audited | Audited, in two formats |
| Maintainability | Single code path | Violates the brief's traceability principle offline | Duplicate logic |
| Lock-in | None | None | None |

## More Information

- [ADR-0017](0017-audit-hash-chain-per-tenant.md)
- [Architecture overview](../architecture/README.md), section 2
