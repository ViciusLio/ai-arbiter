# Detection of personal data: what was measured

> Arbiter is a support tool. It does not provide legal advice. These figures say how
> two detectors did on a small set of invented sentences. They do not say that
> personal data will be found in your prompts.

Measured on 2026-10-05 with `scripts/measure_pii.py`, on the
sentences of `evaluation/pii/`. Versions: presidio-analyzer 2.2.364, spacy 3.8.16, en-core-web-md 3.8.0, it-core-news-md 3.8.0.

## How to read it

- **Recall**: of what should have been found, how much was. A low recall means
  personal data that leaves unmasked.
- **Precision**: of what was flagged, how much was right. A low precision means
  ordinary words masked, and a model that gets less context.
- A detection counts when it overlaps a label of the same category. Exact
  boundaries are not required, which is lenient.
- `builtin` finds formats and validates them. `presidio` is `builtin` plus a
  statistical language model for names and places (ADR-0055).
- Group affiliations (a nationality, a religious or political group) are off by
  default, so `group_affiliation` shows a recall of 0% below. Switched on, on
  2026-10-05 the English model found 2 of 3 and was right in 2 detections of 5:
  it also marked adjectives such as "European". Switch it on with
  `redaction.detector_settings.entities: [PERSON, LOCATION, NRP]`.

## Limits of this measurement

- The set is small: about fifty sentences per language.
- The sentences are synthetic and were written by the author of the detectors.
  Real prompts are longer, messier and mix languages.
- Health data and the other special categories are in no category here: neither
  detector looks for them.
- The time is that of one short sentence on the machine of the measurement, with
  the models already loaded. Loading them takes several seconds, once per process.

## Summary

| Detector | Language | Recall | Precision | Clean texts flagged | Median ms per text |
|---|---|---:|---:|---:|---:|
| `builtin` | English | 14% | 100% | 0 of 15 | 0.0 |
| `builtin` | Italian | 17% | 100% | 0 of 15 | 0.0 |
| `presidio` | English | 81% | 97% | 1 of 15 | 5.5 |
| `presidio` | Italian | 93% | 93% | 0 of 15 | 6.6 |

## By category

### `builtin`, English

49 texts. 0 of the 15 texts with no personal data were flagged. Median time for one text: 0.0 ms.

| Category | To find | Found | Recall | Detections | Right | Precision |
|---|---:|---:|---:|---:|---:|---:|
| `email` | 2 | 2 | 100% | 2 | 2 | 100% |
| `group_affiliation` | 3 | 0 | 0% | 0 | 0 | - |
| `iban` | 1 | 1 | 100% | 1 | 1 | 100% |
| `location` | 14 | 0 | 0% | 0 | 0 | - |
| `payment_card` | 1 | 1 | 100% | 1 | 1 | 100% |
| `person_name` | 20 | 0 | 0% | 0 | 0 | - |
| `phone` | 2 | 2 | 100% | 2 | 2 | 100% |
| **all** | 43 | 6 | 14% | 6 | 6 | 100% |

### `builtin`, Italian

47 texts. 0 of the 15 texts with no personal data were flagged. Median time for one text: 0.0 ms.

| Category | To find | Found | Recall | Detections | Right | Precision |
|---|---:|---:|---:|---:|---:|---:|
| `email` | 2 | 2 | 100% | 2 | 2 | 100% |
| `iban` | 1 | 1 | 100% | 1 | 1 | 100% |
| `it_fiscal_code` | 1 | 1 | 100% | 1 | 1 | 100% |
| `location` | 14 | 0 | 0% | 0 | 0 | - |
| `payment_card` | 1 | 1 | 100% | 1 | 1 | 100% |
| `person_name` | 20 | 0 | 0% | 0 | 0 | - |
| `phone` | 2 | 2 | 100% | 2 | 2 | 100% |
| **all** | 41 | 7 | 17% | 7 | 7 | 100% |

### `presidio`, English

49 texts. 1 of the 15 texts with no personal data were flagged. Median time for one text: 5.5 ms.

| Category | To find | Found | Recall | Detections | Right | Precision |
|---|---:|---:|---:|---:|---:|---:|
| `email` | 2 | 2 | 100% | 2 | 2 | 100% |
| `group_affiliation` | 3 | 0 | 0% | 0 | 0 | - |
| `iban` | 1 | 1 | 100% | 1 | 1 | 100% |
| `location` | 14 | 10 | 71% | 10 | 10 | 100% |
| `payment_card` | 1 | 1 | 100% | 1 | 1 | 100% |
| `person_name` | 20 | 19 | 95% | 20 | 19 | 95% |
| `phone` | 2 | 2 | 100% | 2 | 2 | 100% |
| **all** | 43 | 35 | 81% | 36 | 35 | 97% |

### `presidio`, Italian

47 texts. 0 of the 15 texts with no personal data were flagged. Median time for one text: 6.6 ms.

| Category | To find | Found | Recall | Detections | Right | Precision |
|---|---:|---:|---:|---:|---:|---:|
| `email` | 2 | 2 | 100% | 2 | 2 | 100% |
| `iban` | 1 | 1 | 100% | 1 | 1 | 100% |
| `it_fiscal_code` | 1 | 1 | 100% | 1 | 1 | 100% |
| `location` | 14 | 12 | 86% | 13 | 12 | 92% |
| `payment_card` | 1 | 1 | 100% | 1 | 1 | 100% |
| `person_name` | 20 | 19 | 95% | 21 | 19 | 90% |
| `phone` | 2 | 2 | 100% | 2 | 2 | 100% |
| **all** | 41 | 38 | 93% | 41 | 38 | 93% |

To repeat it: `uv run --group pii-models python scripts/measure_pii.py --write`.

---

*Arbiter is a support tool and does not provide legal advice.*
