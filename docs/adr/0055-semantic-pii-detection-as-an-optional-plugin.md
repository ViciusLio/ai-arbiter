---
status: accepted
date: 2026-10-05
decision-makers: Project owner
---

# 0055: Personal data written in words is detected by an optional local plugin

## Context and Problem Statement

The built-in detectors recognise personal data by its format: e-mail addresses, phone
numbers, IBANs, payment cards, Italian fiscal codes and VAT numbers, IP addresses,
credential formats (ADR-0014, ADR-0027). They do not recognise a name, a postal address
or a health condition written in words, because that is a matter of meaning and not of
format. It is the weakness users will meet first: redaction is on by default, and what
it misses leaves the organisation.

The core already has the place for an answer: a detector is a plugin behind the
`PIIDetector` port, chosen by configuration (ADR-0011). The base install must stay free
of heavy dependencies.

## Considered Options

- **1.** A plugin on Microsoft Presidio with spaCy models for Italian and English, run
  locally, added to the built-in detectors.
- **2.** spaCy alone.
- **3.** GLiNER, a small multilingual model that finds entities named at run time.
- **4.** A local language model used as a detector.
- **5.** A cloud service (Azure AI Language).

## Decision Outcome

Chosen option: **1**.

- A new optional extra, `pii`, brings Presidio and spaCy. The plugin is named in
  `plugins.pii_detector`; nothing changes for an install without the extra.
- The plugin **adds to** the built-in detectors, it does not replace them: formats are
  still found by the detectors that validate them (a checksum for an IBAN), and the
  plugin contributes what only meaning can find, names and places first.
- Everything runs in the process. No text leaves the machine, and no text is stored:
  the detector returns categories and positions, as the built-in ones do.
- The language models are not shipped with the package and are not downloaded silently:
  the operator installs them, and the plugin says which one is missing.
- **Precision and recall are measured and published**, per category and per language,
  on a labelled set of synthetic sentences kept in the repository (I-13). Without
  numbers nobody can tell whether the plugin improves anything, and the limits of
  detection must be shown to users (ADR-0014).

### Consequences

- Good: names and places written in words are found, with no data leaving.
- Good: the limits become numbers that can be compared from one release to the next.
- Bad: the models weigh hundreds of megabytes and add time to every request; the
  measurement reports that time too.
- Bad: a statistical detector misses things and flags things that are not personal
  data. Its findings are redacted like any other, so a false positive costs the model
  some context.

## Pros and Cons of the Options

| Criterion | 1. Presidio and spaCy | 2. spaCy alone | 3. GLiNER | 4. Local language model | 5. Cloud service |
|---|---|---|---|---|---|
| Complexity | Medium | Low | Medium | High | Low |
| Azure cost | None | None | None | None | Per request |
| Scalability | Tens of milliseconds per request | A little faster | Slower, heavier | Slow on every request | Limited by quotas |
| Security | No data leaves | No data leaves | No data leaves | No data leaves | Prompts go to a service |
| Compliance / privacy | Local; limits measurable | As 1, fewer categories | Local; possibly the best recall | Not reproducible | A further processor of personal data |
| Maintainability | A maintained framework with recognisers per country | Fewer recognisers to rely on | PyTorch to carry | Prompts to keep working | An adapter to keep |
| Lock-in | Low: behind the port | Low | Medium | Medium | High |

## More Information

- [ADR-0014](0014-pii-detection-built-in-and-pluggable.md), [ADR-0027](0027-pii-detectors-core-and-deferrable.md),
  [ADR-0011](0011-plugins-via-entry-points-and-config.md); improvements I-04 and I-13 in
  the README
