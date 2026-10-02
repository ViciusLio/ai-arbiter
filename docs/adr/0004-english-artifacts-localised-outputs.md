---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0004: Write artifacts in English; localise user-facing outputs in EN and IT

## Context and Problem Statement

The brief is in Italian, while the project targets an international open source audience.
Digests and reports are read by end users, including non-technical ones, in their own
language.

## Considered Options

- **A.** English for code, README, documentation and ADRs.
- **B.** Italian throughout.
- **C.** Fully bilingual repository.

## Decision Outcome

Chosen option: **A**, with one addition from the project owner: **user-facing outputs
(digests, reports) are localised in English and Italian** from v0.1.

- English: code, identifiers, comments, commit messages, README, docs, ADRs, CHANGELOG.
- Localised (EN, IT): digest, reports, classifier rationales, finding titles and
  recommended actions, CLI output meant for end users.
- Unchanged: `docs/PROJECT_BRIEF.md` and `docs/phases/phase-0-analysis.md` stay in Italian
  as historical records.

### Consequences

- Good: one language to maintain for everything developers read.
- Bad: every user-facing string, including rule pack messages, needs an EN and an IT
  entry; a test enforces key parity.
- Follow-up: mechanism in [ADR-0021](0021-i18n-message-catalogs.md).

## Pros and Cons of the Options

The technical criteria of the brief (cost, scalability, security, lock-in) do not
discriminate between these options.

| Criterion | A. English | B. Italian | C. Bilingual |
|---|---|---|---|
| Audience | International | Small | Largest |
| Maintainability | One language | One language | Every document twice |
| Consistency with ecosystem | High | Low | High |

## More Information

- [Phase 0 analysis](../phases/phase-0-analysis.md), section 8 (D3)
