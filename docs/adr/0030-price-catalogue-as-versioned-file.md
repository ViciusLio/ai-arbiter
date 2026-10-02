---
status: accepted
date: 2026-10-02
decision-makers: Project owner
---

# 0030: Keep prices in a versioned YAML catalogue and convert currency only when reporting

## Context and Problem Statement

FinOps attributes a cost to every interaction. Prices change, differ by region and by
deployment type, and are published by providers in their own currency. A cost shown in a
report must be reproducible: it must be possible to say which prices produced it.

## Considered Options

- **A.** A versioned YAML file shipped with the package like a rule pack, with overrides
  in configuration.
- **B.** A database table managed through the API.
- **C.** Importing a third-party price list.

## Decision Outcome

Chosen option: **A**.

Catalogue:

- A catalogue is a YAML file with a name, a version, a currency, an `as_of` date and a
  list of prices. Each price names the provider, the model, optionally a region, and the
  price per million tokens for input, output and, where the provider distinguishes them,
  cached input.
- Prices are decimal strings and are read as `Decimal`. A price written as a YAML float
  is refused when the catalogue is loaded.
- A price with a region wins over a price without one for the same provider and model.
- Configuration can add or replace prices (`finops.prices`). The effective version
  recorded on interactions is then the catalogue version followed by a short digest of
  the overrides, so that two different sets of prices never share a version.
- The catalogue shipped with the package prices only the mock provider. Arbiter does not
  ship the price lists of real providers: they change without notice and a wrong price
  presented as current would mislead. The operator enters the prices of the deployments
  in use.
- A model with no price is not an error. The interaction is recorded with its token
  counts and no cost, and reports count it as unpriced.

Cost and currency:

- The cost of an interaction is computed once, when it is recorded, in the currency of
  the catalogue, and stored with that currency and the catalogue version. Every cost is
  an estimate and is labelled as such.
- Amounts are stored as integers scaled by 10^9, so that sums are exact on PostgreSQL and
  on SQLite, and are handled as `Decimal` in code.
- A tenant has at most one reporting currency other than the catalogue's, with an
  explicit conversion rate and the date of that rate, set in configuration. Reports show
  the catalogue amount and the converted amount, and state the rate and its date. With
  no rate configured, reports stay in the catalogue currency.
- A budget is expressed in the catalogue currency or in the reporting currency.

### Consequences

- Good: a cost can always be traced to a catalogue version that is a file under version
  control.
- Good: no price administration to secure and audit in v0.1.
- Bad: prices are updated by editing a file or configuration, and a restart.
- Bad: with no shipped prices for real providers, a new installation reports real
  traffic as unpriced until prices are entered. The usage report says so.
- Bad: one fixed conversion rate is an approximation; the report states it.

## Pros and Cons of the Options

| Criterion | A. Versioned YAML file | B. Database table and API | C. Third-party import |
|---|---|---|---|
| Complexity | Low | Medium: endpoints, migration, history | Medium: format mapping |
| Azure cost | None | None | None |
| Scalability | In memory | Cached reads | In memory |
| Security | Changes are reviewed like code | Needs a role and audited changes | External data to validate |
| Compliance / privacy | Version reproducible on every interaction | Version rebuilt from history | Prices of unknown freshness, origin to declare |
| Maintainability | Prices edited by hand | Updated without a release | Follows someone else's format |
| Lock-in | None | None | On the source |

## More Information

- [Data model](../architecture/data-model.md): "price catalogues are files, not tables"
- [Phase 0 analysis](../phases/phase-0-analysis.md), item A15
