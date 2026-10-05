"""Personal data written in words, found with Presidio and spaCy, run locally (ADR-0055).

The plugin adds to the built-in detectors: formats are still found by the detectors that
validate them, and this one contributes what only meaning can find. Presidio, spaCy and
the language models are part of the ``pii`` extra and are loaded when a text is first
analysed, so that naming this plugin on an install without them fails with an
instruction. Nothing leaves the process and no text is kept.
"""

import re
from collections.abc import Mapping, Sequence
from functools import cache
from typing import Any

from ai_arbiter.core.errors import ConfigurationError, MissingExtraError
from ai_arbiter.core.redaction.builtin import BuiltinDetector
from ai_arbiter.core.redaction.model import DetectorInfo, PIISpan

_FEATURE = "Semantic detection of personal data"

# What Presidio calls an entity, and the category Arbiter reports it under.
ENTITY_CATEGORIES: Mapping[str, str] = {
    "PERSON": "person_name",
    "LOCATION": "location",
    # Nationality, religious or political group.
    "NRP": "group_affiliation",
}
DEFAULT_MODELS: Mapping[str, str] = {"en": "en_core_web_md", "it": "it_core_news_md"}
# Group affiliations are off unless asked for: when measured, six detections in ten
# were ordinary adjectives such as "European" (docs/pii-evaluation.md).
DEFAULT_ENTITIES = ("PERSON", "LOCATION")
_WORD = re.compile(r"[^\W\d_]+")

_INFO = (
    DetectorInfo(
        category="person_name",
        validates="A statistical language model marks a span as the name of a person.",
        misses=(
            "Names the model does not know, names in lower case or inside identifiers, "
            "initials and nicknames. Words that are not names are sometimes marked too."
        ),
    ),
    DetectorInfo(
        category="location",
        validates="A statistical language model marks a span as a place.",
        misses=(
            "Street addresses as a whole: a city is usually found, a street and a house "
            "number often are not. A place is not always personal data."
        ),
    ),
    DetectorInfo(
        category="group_affiliation",
        validates=(
            "A statistical language model marks a nationality or a religious or political "
            "group. English only."
        ),
        misses="Anything said indirectly. Health data and other special categories are not found.",
    ),
)


@cache
def _load(models: tuple[tuple[str, str], ...]) -> tuple[Any, dict[str, frozenset[str]]]:
    """The analyzer for these language models, and the common words of each language.

    Loaded once per process and shared: a language model takes hundreds of megabytes,
    and two detectors with the same models must not hold two copies.
    """
    try:
        import spacy.util
        from presidio_analyzer import AnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
    except ImportError as exc:
        raise MissingExtraError("pii", _FEATURE) from exc
    missing = [model for _, model in models if not spacy.util.is_package(model)]
    if missing:
        # A model is never downloaded behind the operator's back.
        raise ConfigurationError(
            f"the language model '{missing[0]}' is not installed: install it, or name "
            "the installed ones in redaction.detector_settings.models"
        )
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": language, "model_name": model} for language, model in models],
        }
    )
    languages = [language for language, _ in models]
    engine = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=languages)
    stop_words = {
        language: frozenset(spacy.util.get_lang_class(language).Defaults.stop_words)
        for language in languages
    }
    return engine, stop_words


class PresidioDetector:
    """Registered as ``presidio``. The built-in detectors, plus names and places."""

    name = "presidio"

    def __init__(
        self,
        *,
        models: Mapping[str, str] | None = None,
        entities: Sequence[str] | None = None,
        min_score: float = 0.5,
    ) -> None:
        self._models = dict(models) if models is not None else dict(DEFAULT_MODELS)
        self._entities = list(entities) if entities is not None else list(DEFAULT_ENTITIES)
        unknown = sorted(set(self._entities) - set(ENTITY_CATEGORIES))
        if unknown or not self._models or not 0 <= min_score <= 1:
            raise ConfigurationError(
                "redaction.detector_settings: 'entities' may hold "
                f"{', '.join(ENTITY_CATEGORIES)}; 'models' maps a language to a spaCy "
                "model; 'min_score' is between 0 and 1"
            )
        self._min_score = min_score
        self._builtin = BuiltinDetector()
        self._engine: Any = None
        self._stop_words: dict[str, frozenset[str]] = {}

    def _analyzer(self) -> Any:
        if self._engine is None:
            self._engine, self._stop_words = _load(tuple(sorted(self._models.items())))
        return self._engine

    def _languages_of(self, text: str) -> list[str]:
        """The configured languages a text should be read in.

        A model reading a language it was not trained on marks ordinary words as names.
        So the text goes to the model of the language whose common words it uses most,
        and to every model only when it uses none of them, a bare name for example.
        """
        words = set(_WORD.findall(text.lower()))
        scores = {
            language: len(words & stop_words) for language, stop_words in self._stop_words.items()
        }
        best = max(scores.values(), default=0)
        if best == 0:
            return sorted(self._models)
        return sorted(language for language, score in scores.items() if score == best)

    def detect(self, text: str, *, locale: str | None = None) -> Sequence[PIISpan]:
        found = list(self._builtin.detect(text, locale=locale))
        if not text.strip():
            return found
        analyzer = self._analyzer()
        languages = [locale] if locale in self._models else self._languages_of(text)
        semantic: list[PIISpan] = []
        for language in languages:
            for result in analyzer.analyze(text=text, language=language, entities=self._entities):
                if result.score >= self._min_score:
                    semantic.append(
                        PIISpan(
                            category=ENTITY_CATEGORIES[result.entity_type],
                            start=result.start,
                            end=result.end,
                            confidence=float(result.score),
                        )
                    )
        # A format the built-in detectors validated wins over a guess on the same text.
        taken = [(span.start, span.end) for span in found]
        for span in sorted(semantic, key=lambda s: (-s.confidence, -(s.end - s.start), s.start)):
            if all(span.end <= start or span.start >= end for start, end in taken):
                found.append(span)
                taken.append((span.start, span.end))
        return sorted(found, key=lambda span: span.start)

    def describe(self) -> Sequence[DetectorInfo]:
        wanted = {ENTITY_CATEGORIES[entity] for entity in self._entities}
        return [*self._builtin.describe(), *(info for info in _INFO if info.category in wanted)]
