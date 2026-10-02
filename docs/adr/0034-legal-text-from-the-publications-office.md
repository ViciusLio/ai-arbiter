---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0034: Take the legal text from the Publications Office and have the owner confirm it on EUR-Lex

## Context and Problem Statement

AI Act rules must be written from the official EU text, and the working rule of the
project names EUR-Lex. The EUR-Lex website answers automated requests with a verification
page and no content. The Publications Office of the European Union serves the same
Official Journal documents, addressed by CELEX number, from the repository EUR-Lex itself
draws on.

## Considered Options

- **1.** Use the Publications Office, by CELEX number.
- **2.** The owner downloads the texts from EUR-Lex into the repository.
- **3.** The Publications Office for the work, and the owner spot-checks on EUR-Lex the
  articles a rule pack quotes.

## Decision Outcome

Chosen option: **3**.

- A legal rule pack lists its sources: CELEX number, title, retrieval date, URL and the
  SHA-256 of the file retrieved.
- It declares `verified_against: primary` when it was written from those texts, and
  `review: pending` until the owner has compared the quoted articles on EUR-Lex; then
  `review: confirmed`, with the date.
- Every output built on a pack whose review is pending says so.
- The Official Journal text is the authentic one. A consolidated text is used to read
  amended articles in one place and is checked against the amending act.
- The check is repeated at every release of a legal rule pack, including a search for
  corrigenda and later amending acts.

### Consequences

- Good: the retrieval can be repeated by script, and its result is pinned by checksum.
- Good: a person confirms the text on the site the rule names.
- Bad: until the owner's check, outputs carry a "review pending" notice.
- Bad: the check covers the articles quoted, not the whole Regulation.

## Pros and Cons of the Options

| Criterion | 1. Publications Office (CELLAR) by CELEX number | 2. The owner downloads the texts from EUR-Lex into the repository | 3. CELLAR for the work, and the owner spot-checks listed articles on EUR-Lex |
|---|---|---|---|
| Complexity | Lowest: already done | A manual step at every rule pack release | Low |
| Azure cost | None | None | None |
| Scalability | Repeatable by script at every release | Depends on a person | Repeatable, with a short manual step |
| Security | Official EU domain; checksum recorded | Same documents | Same |
| Compliance / privacy | Same documents as EUR-Lex, but not the site the rule names | Matches the rule to the letter | Matches the rule, with evidence of a human check |
| Maintainability | Good | Poor | Good |
| Lock-in | None | None | None |

## More Information

- [Phase 4 preparation](../phases/phase-4-preparation.md), decision P4-1
