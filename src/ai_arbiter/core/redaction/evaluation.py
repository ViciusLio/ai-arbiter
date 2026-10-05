"""Measure a detector of personal data against texts that say what should be found.

A labelled text marks what a detector should find as ``[text](category)``. Precision and
recall are computed per category on spans: a detection counts when it overlaps a label
of the same category, so a detector is not punished for including a title or a house
number that the label left out. That choice is lenient and is stated wherever the
figures are shown (ADR-0014, ADR-0055).
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from ai_arbiter.core.redaction.model import PIIDetector, PIISpan

_LABEL = re.compile(r"\[([^\]]+)\]\(([a-z_]+)\)")


@dataclass(frozen=True)
class LabelledText:
    text: str
    # What should be found: category and position in ``text``.
    expected: tuple[tuple[str, int, int], ...]


@dataclass
class Score:
    """Counts for one category, or for all of them together."""

    expected: int = 0
    found: int = 0  # labels a detection overlapped
    detected: int = 0
    correct: int = 0  # detections that overlapped a label

    @property
    def recall(self) -> float | None:
        """The share of what should be found that was. ``None`` with nothing to find."""
        return self.found / self.expected if self.expected else None

    @property
    def precision(self) -> float | None:
        """The share of detections that were right. ``None`` with no detection."""
        return self.correct / self.detected if self.detected else None


@dataclass
class Evaluation:
    texts: int = 0
    # Texts with no label on which the detector found something anyway.
    clean_texts: int = 0
    clean_texts_flagged: int = 0
    by_category: dict[str, Score] = field(default_factory=dict)

    @property
    def total(self) -> Score:
        total = Score()
        for score in self.by_category.values():
            total.expected += score.expected
            total.found += score.found
            total.detected += score.detected
            total.correct += score.correct
        return total


def parse_labelled(line: str) -> LabelledText:
    """Read one labelled line into its plain text and the spans to find."""
    text = ""
    expected: list[tuple[str, int, int]] = []
    position = 0
    for match in _LABEL.finditer(line):
        text += line[position : match.start()]
        start = len(text)
        text += match.group(1)
        expected.append((match.group(2), start, len(text)))
        position = match.end()
    text += line[position:]
    return LabelledText(text=text, expected=tuple(expected))


def read_labelled(lines: Iterable[str]) -> list[LabelledText]:
    """Labelled texts, one per line. Empty lines and lines that start with ``#`` are skipped."""
    return [
        parse_labelled(line.strip())
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _overlaps(start: int, end: int, other_start: int, other_end: int) -> bool:
    return start < other_end and other_start < end


def evaluate(
    detector: PIIDetector, texts: Sequence[LabelledText], *, locale: str | None = None
) -> Evaluation:
    """Run the detector on every text and count what it found and what it missed."""
    result = Evaluation()
    for item in texts:
        spans: Sequence[PIISpan] = detector.detect(item.text, locale=locale)
        result.texts += 1
        if not item.expected:
            result.clean_texts += 1
            result.clean_texts_flagged += bool(spans)
        for category, start, end in item.expected:
            score = result.by_category.setdefault(category, Score())
            score.expected += 1
            score.found += any(
                span.category == category and _overlaps(span.start, span.end, start, end)
                for span in spans
            )
        for span in spans:
            score = result.by_category.setdefault(span.category, Score())
            score.detected += 1
            score.correct += any(
                category == span.category and _overlaps(span.start, span.end, start, end)
                for category, start, end in item.expected
            )
    return result
