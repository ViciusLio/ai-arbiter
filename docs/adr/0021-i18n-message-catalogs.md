---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0021 — Localise outputs with keyed YAML catalogues and Babel for formatting

## Context and Problem Statement

ADR-0004 requires digests, reports and classifier output in English and Italian. The text
comes from three places: templates, rule packs (titles, rationales, recommended actions)
and code (CLI messages). Dates, numbers and currency amounts must follow the locale.

## Considered Options

- **A.** Message catalogues as YAML files keyed by message id (`locales/en.yaml`,
  `locales/it.yaml`), referenced from templates and rule packs through `message_key`;
  Babel for dates, numbers and currency.
- **B.** gettext `.po`/`.mo` catalogues with the Jinja2 i18n extension.
- **C.** One template per language.

## Decision Outcome

Chosen option: **A**.

- Rule packs never contain user-facing prose; they reference `message_key`. A rule pack
  ships with its own catalogue files, so a third-party pack brings its translations.
- A test fails if the EN and IT catalogues do not have the same keys and placeholders.
- The locale is chosen per output: `--locale` on the CLI, a field on digest
  subscriptions, `Accept-Language` on report endpoints. English is the fallback.
- API error messages and logs stay in English.
- Legal references are data, not translated text: article numbers are stored once and
  rendered by locale ("Article 50(1)" / "art. 50, par. 1").

### Consequences

- Good: no compile step; catalogues are reviewable in a pull request by a non-developer.
- Good: adding a language is adding a file.
- Bad: no plural rules as rich as gettext's; messages are written to avoid
  count-dependent grammar, with explicit `one`/`other` variants where unavoidable.
- Bad: no existing translator tooling for the format.
- Future alternative (noted at acceptance): if translators join the project, gettext
  `.po` catalogues (option B) become the better choice, because translation tools and
  platforms work with them. The message keys are stable identifiers, so the catalogues
  can be converted mechanically; that change would be a new ADR superseding this one.

## Pros and Cons of the Options

| Criterion | A. Keyed YAML + Babel | B. gettext | C. Template per language |
|---|---|---|---|
| Complexity | Low | Medium (extraction, compilation in the build) | Low at first |
| Azure cost | None | None | None |
| Scalability | Loaded once at startup | Same | Same |
| Security | Data files only | Same | Templates are code-like |
| Compliance / privacy | Legal wording reviewable per key | Same, via `.po` files | Wording drifts between copies |
| Maintainability | Key parity enforced by a test | Mature tooling; binary artefacts to build | Every layout change made twice |
| Lock-in | Own format | Standard | None |

## More Information

- [ADR-0004](0004-english-artifacts-localised-outputs.md)
