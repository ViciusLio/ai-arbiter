"""Measuring a detector on labelled texts, and the semantic detector itself (ADR-0055)."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from ai_arbiter.core.config import load_settings
from ai_arbiter.core.errors import ConfigurationError
from ai_arbiter.core.plugins.detectors import load_detector
from ai_arbiter.core.plugins.registry import PluginRegistry
from ai_arbiter.core.redaction.builtin import BuiltinDetector
from ai_arbiter.core.redaction.evaluation import (
    LabelledText,
    evaluate,
    parse_labelled,
    read_labelled,
)
from ai_arbiter.core.redaction.model import DetectorInfo, PIISpan

SENTENCES = Path(__file__).parents[2] / "evaluation" / "pii"


def test_a_labelled_line_becomes_plain_text_and_the_spans_to_find() -> None:
    labelled = parse_labelled("Write to [Mary Johnson](person_name) in [Leeds](location) today.")

    assert labelled.text == "Write to Mary Johnson in Leeds today."
    assert labelled.expected == (("person_name", 9, 21), ("location", 25, 30))
    assert labelled.text[9:21] == "Mary Johnson"
    assert parse_labelled("Nothing to find here.") == LabelledText("Nothing to find here.", ())


def test_comments_and_empty_lines_are_not_texts() -> None:
    texts = read_labelled(["# a comment", "", "  ", "One [x@example.org](email).", "Two."])

    assert [item.text for item in texts] == ["One x@example.org.", "Two."]


class Fixed:
    """A detector that returns what the test tells it to."""

    name = "fixed"

    def __init__(self, spans: dict[str, list[PIISpan]]) -> None:
        self._spans = spans

    def detect(self, text: str, *, locale: str | None = None) -> Sequence[PIISpan]:
        return self._spans.get(text, [])

    def describe(self) -> Sequence[DetectorInfo]:
        return []


def span(category: str, start: int, end: int) -> PIISpan:
    return PIISpan(category=category, start=start, end=end, confidence=0.9)


def test_recall_and_precision_are_counted_per_category_on_overlapping_spans() -> None:
    texts = read_labelled(
        [
            "Write to [Mary Johnson](person_name) in [Leeds](location).",
            "Call [Tom Reid](person_name).",
            "Summarise the Aurora release.",
        ]
    )
    detector = Fixed(
        {
            # The name with its title is still the name; the place is missed.
            texts[0].text: [span("person_name", 6, 21)],
            # A place where there is a name: wrong category.
            texts[1].text: [span("location", 5, 13)],
            # Something where there is nothing.
            texts[2].text: [span("person_name", 14, 20)],
        }
    )

    result = evaluate(detector, texts)

    names, places = result.by_category["person_name"], result.by_category["location"]
    assert (names.expected, names.found, names.detected, names.correct) == (2, 1, 2, 1)
    assert (names.recall, names.precision) == (0.5, 0.5)
    assert (places.expected, places.found, places.detected, places.correct) == (1, 0, 1, 0)
    assert (result.texts, result.clean_texts, result.clean_texts_flagged) == (3, 1, 1)
    assert (result.total.expected, result.total.correct) == (3, 1)


def test_figures_that_cannot_be_computed_are_absent_and_not_zero() -> None:
    result = evaluate(Fixed({}), read_labelled(["Nothing here."]))

    assert result.by_category == {}
    assert (result.total.recall, result.total.precision) == (None, None)


@pytest.mark.parametrize("language", ["en", "it"])
def test_the_labelled_sentences_are_well_formed_and_the_formats_in_them_are_found(
    language: str,
) -> None:
    texts = read_labelled((SENTENCES / f"{language}.txt").read_text(encoding="utf-8").splitlines())

    result = evaluate(BuiltinDetector(), texts)

    assert len(texts) >= 45
    assert sum(1 for item in texts if not item.expected) == 15
    assert all("](" not in item.text for item in texts)
    # The built-in detectors find every format and nothing else: no name, no place.
    for category in ("email", "phone", "iban", "payment_card"):
        assert result.by_category[category].recall == 1.0, category
    assert result.by_category["person_name"].found == 0
    assert result.total.precision == 1.0
    assert result.clean_texts_flagged == 0


def test_detector_settings_reach_the_detector_and_the_built_in_one_takes_none() -> None:
    registry = PluginRegistry()

    assert load_detector(registry, load_settings()).name == "builtin"
    with pytest.raises(ConfigurationError, match="does not take these settings"):
        load_detector(registry, load_settings(redaction={"detector_settings": {"x": 1}}))


def presidio() -> type:
    pytest.importorskip("presidio_analyzer", reason="needs the pii extra")
    spacy_util = pytest.importorskip("spacy.util")
    if not (spacy_util.is_package("en_core_web_md") and spacy_util.is_package("it_core_news_md")):
        pytest.skip("needs the language models of the pii-models group")
    from ai_arbiter.adapters.presidio.detector import PresidioDetector

    return PresidioDetector


def found(detector: object, text: str) -> list[tuple[str, str]]:
    spans = detector.detect(text)  # type: ignore[attr-defined]
    return [(item.category, text[item.start : item.end]) for item in spans]


def test_names_and_places_written_in_words_are_found_next_to_the_formats() -> None:
    detector = presidio()()

    italian = found(
        detector, "Scrivi a Maria Rossi (maria.rossi@example.com), che abita a Bologna."
    )
    english = found(detector, "Ask John Smith in Dublin to send IT60X0542811101000000123456.")

    assert italian == [
        ("person_name", "Maria Rossi"),
        ("email", "maria.rossi@example.com"),
        ("location", "Bologna"),
    ]
    assert english == [
        ("person_name", "John Smith"),
        ("location", "Dublin"),
        ("iban", "IT60X0542811101000000123456"),
    ]


def test_a_text_is_read_by_the_model_of_its_language_only() -> None:
    detector = presidio()()

    # The English model would take this whole Italian sentence for a name.
    assert found(detector, "Riassumi il verbale della riunione di ieri.") == []
    assert found(detector, "Summarise the minutes of yesterday's meeting.") == []
    # A bare name uses the common words of no language: every model reads it.
    assert found(detector, "Maria Rossi") == [("person_name", "Maria Rossi")]


def test_the_detector_describes_its_limits_and_groups_are_off_until_asked_for() -> None:
    plugin = presidio()
    default = plugin()
    with_groups = plugin(entities=["PERSON", "LOCATION", "NRP"])
    text = "The applicant says she is Catholic."

    assert [info.category for info in default.describe()][-2:] == ["person_name", "location"]
    assert "group_affiliation" in [info.category for info in with_groups.describe()]
    assert ("group_affiliation", "Catholic") not in found(default, text)
    assert ("group_affiliation", "Catholic") in found(with_groups, text)
    assert all(info.misses for info in with_groups.describe())


def test_settings_the_detector_cannot_use_are_refused_and_a_model_is_never_downloaded() -> None:
    plugin = presidio()

    with pytest.raises(ConfigurationError, match="entities"):
        plugin(entities=["CREDIT_SCORE"])
    with pytest.raises(ConfigurationError, match="min_score"):
        plugin(min_score=2)
    missing = plugin(models={"en": "en_core_web_trf"})
    with pytest.raises(ConfigurationError, match="'en_core_web_trf' is not installed"):
        missing.detect("Ask John Smith.")
