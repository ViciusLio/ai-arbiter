"""Measure the detectors of personal data on the labelled sentences of evaluation/pii.

    uv run --group pii-models python scripts/measure_pii.py            # print the figures
    uv run --group pii-models python scripts/measure_pii.py --write    # docs/pii-evaluation.md

For each detector and each language: recall and precision per category, how many texts
with no personal data were flagged anyway, and the time one text takes. Run by hand; it
needs the `pii` extra and the language models, so it is not part of the test suite.

Arbiter is a support tool and does not provide legal advice.
"""

import argparse
import statistics
import sys
import time
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

from ai_arbiter.core.plugins.registry import PII_DETECTORS, PluginRegistry
from ai_arbiter.core.redaction.evaluation import Evaluation, Score, evaluate, read_labelled
from ai_arbiter.core.redaction.model import PIIDetector

ROOT = Path(__file__).parents[1]
SENTENCES = ROOT / "evaluation" / "pii"
REPORT = ROOT / "docs" / "pii-evaluation.md"
DETECTORS = ("builtin", "presidio")
LANGUAGES = {"en": "English", "it": "Italian"}


def percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.0f}%"


def row(category: str, score: Score) -> str:
    return (
        f"| `{category}` | {score.expected} | {score.found} | {percent(score.recall)} | "
        f"{score.detected} | {score.correct} | {percent(score.precision)} |"
    )


def timed(detector: PIIDetector, texts: list[str]) -> float:
    """Median time for one text, in milliseconds, over three passes."""
    detector.detect("warm up")
    samples = []
    for _ in range(3):
        for text in texts:
            started = time.perf_counter()
            detector.detect(text)
            samples.append((time.perf_counter() - started) * 1000)
    return statistics.median(samples)


def section(name: str, language: str, result: Evaluation, milliseconds: float) -> list[str]:
    lines = [
        f"### `{name}`, {LANGUAGES[language]}",
        "",
        f"{result.texts} texts. {result.clean_texts_flagged} of the {result.clean_texts} "
        f"texts with no personal data were flagged. Median time for one text: "
        f"{milliseconds:.1f} ms.",
        "",
        "| Category | To find | Found | Recall | Detections | Right | Precision |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    lines += [row(category, score) for category, score in sorted(result.by_category.items())]
    lines += [row("all", result.total).replace("`all`", "**all**"), ""]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help=f"Write {REPORT.name}.")
    arguments = parser.parse_args()

    registry = PluginRegistry()
    sets = {
        language: read_labelled(
            (SENTENCES / f"{language}.txt").read_text(encoding="utf-8").splitlines()
        )
        for language in LANGUAGES
    }
    body: list[str] = []
    summary: list[str] = [
        "| Detector | Language | Recall | Precision | Clean texts flagged | Median ms per text |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name in DETECTORS:
        detector: PIIDetector = registry.load(PII_DETECTORS, name)()
        for language, texts in sets.items():
            result = evaluate(detector, texts)
            milliseconds = timed(detector, [item.text for item in texts])
            total = result.total
            summary.append(
                f"| `{name}` | {LANGUAGES[language]} | {percent(total.recall)} | "
                f"{percent(total.precision)} | {result.clean_texts_flagged} of "
                f"{result.clean_texts} | {milliseconds:.1f} |"
            )
            body += section(name, language, result, milliseconds)

    versions = ", ".join(
        f"{package} {metadata.version(package)}"
        for package in ("presidio-analyzer", "spacy", "en-core-web-md", "it-core-news-md")
    )
    report = [
        "# Detection of personal data: what was measured",
        "",
        "> Arbiter is a support tool. It does not provide legal advice. These figures say how",
        "> two detectors did on a small set of invented sentences. They do not say that",
        "> personal data will be found in your prompts.",
        "",
        f"Measured on {datetime.now(UTC):%Y-%m-%d} with `scripts/measure_pii.py`, on the",
        "sentences of `evaluation/pii/`. Versions: " + versions + ".",
        "",
        "## How to read it",
        "",
        "- **Recall**: of what should have been found, how much was. A low recall means",
        "  personal data that leaves unmasked.",
        "- **Precision**: of what was flagged, how much was right. A low precision means",
        "  ordinary words masked, and a model that gets less context.",
        "- A detection counts when it overlaps a label of the same category. Exact",
        "  boundaries are not required, which is lenient.",
        "- `builtin` finds formats and validates them. `presidio` is `builtin` plus a",
        "  statistical language model for names and places (ADR-0055).",
        "- Group affiliations (a nationality, a religious or political group) are off by",
        "  default, so `group_affiliation` shows a recall of 0% below. Switched on, on",
        "  2026-10-05 the English model found 2 of 3 and was right in 2 detections of 5:",
        '  it also marked adjectives such as "European". Switch it on with',
        "  `redaction.detector_settings.entities: [PERSON, LOCATION, NRP]`.",
        "",
        "## Limits of this measurement",
        "",
        "- The set is small: about fifty sentences per language.",
        "- The sentences are synthetic and were written by the author of the detectors.",
        "  Real prompts are longer, messier and mix languages.",
        "- Health data and the other special categories are in no category here: neither",
        "  detector looks for them.",
        "- The time is that of one short sentence on the machine of the measurement, with",
        "  the models already loaded. Loading them takes several seconds, once per process.",
        "",
        "## Summary",
        "",
        *summary,
        "",
        "## By category",
        "",
        *body,
        "To repeat it: `uv run --group pii-models python scripts/measure_pii.py --write`.",
        "",
        "---",
        "",
        "*Arbiter is a support tool and does not provide legal advice.*",
        "",
    ]
    text = "\n".join(report)
    if arguments.write:
        REPORT.write_text(text, encoding="utf-8", newline="\n")
        sys.stdout.write(f"Wrote {REPORT.relative_to(ROOT)}\n")
    sys.stdout.write("\n".join(summary) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
