---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0012: Use one declarative rule engine in Python for policy, classification and scanning

## Context and Problem Statement

The brief asks to evaluate OPA (Rego) against a Python rule engine for the gateway policy
module. Two further modules need rules: the classifier (ADR-0003 requires rules as
versioned data) and the scanner. All three must explain their outcome, and two of them
must run inside an offline CLI installed with `pip` on Windows, macOS and Linux.

## Considered Options

- **A.** One small declarative engine in `core.rules`: rule packs are YAML files validated
  against a schema; conditions use a closed set of operators over named facts; the engine
  returns the outcome and the trace of matched conditions.
- **B.** OPA with Rego, as sidecar or subprocess.
- **C.** Rules written as Python functions.

## Decision Outcome

Chosen option: **A**, with the `PolicyEngine` port kept open so an OPA adapter can be
added for organisations that already manage Rego.

Shape of the engine:

- **Facts** are produced by code: request attributes, the system's risk profile, PII
  detector results, declared inventory attributes, collector output.
- **Rules** are data. A condition is a tree of `all` / `any` / `not` over comparisons
  (`eq`, `ne`, `in`, `contains`, `gt`, `lt`, `exists`). There is no expression language
  and no code execution.
- **Outcomes** depend on the rule kind: a policy decision, a classification, or a finding.
- Every rule pack declares its version and, for legal packs, the regulation, amending
  acts, the `as_of` date and whether it was verified against the primary source. Every
  rule carries its legal reference and the date the obligation applies from.

```yaml
pack: ai-act
version: 2026.10.0
regulation:
  id: "Regulation (EU) 2024/1689"
  amended_by: ["Digital Omnibus on AI (2026)"]
  as_of: 2026-10-02
  verified_against: secondary        # must be `primary` before release
rules:
  - id: AIA-ART5-1F-EMOTION-WORKPLACE
    kind: classification
    roles: [provider, deployer]
    when:
      all:
        - { fact: capabilities.emotion_recognition, eq: true }
        - { fact: context.setting, in: [workplace, education] }
        - not: { fact: purpose.medical_or_safety, eq: true }
    then:
      outcome: prohibited
      legal_refs: [{ article: "5(1)(f)" }]
      applies_from: 2025-02-02
      message_key: aia.art5.1f.emotion_workplace
```

### Consequences

- Good: one engine, one trace format, one test harness for three modules.
- Good: no binary to distribute; identical behaviour in gateway and CLI.
- Good: rules cannot execute code, so a rule pack from a third party is safe to load.
- Bad: less expressive than Rego; anything the operators cannot express becomes a new
  fact computed in code.
- Bad: a custom format is one more thing to document.

## Pros and Cons of the Options

| Criterion | A. Declarative Python engine | B. OPA / Rego | C. Python functions |
|---|---|---|---|
| Complexity | Medium (engine to write and test) | Medium to high (binary, bundle distribution) | Low |
| Azure cost | None | Sidecar CPU and memory per replica | None |
| Scalability | In-process, microseconds | Fast, plus an IPC hop per evaluation | In-process |
| Security | Data only, no code execution | Sandboxed language, mature | Rule packs are arbitrary code |
| Compliance / privacy | Rules readable by non-developers; full match trace | Decision logs available; Rego hard to read for legal reviewers | Not reviewable as data; violates ADR-0003 |
| Maintainability | Small custom engine | Industry standard, second language to maintain | Easy to write, hard to version |
| Lock-in | Own format, trivially exportable | On OPA | None |
| Offline CLI on Windows | Works | Needs a bundled binary or WASM runtime | Works |

## More Information

- [ADR-0003](0003-deterministic-classifier-rules-as-data.md)
- [Interfaces](../architecture/interfaces.md), section "Rules and decisions"
