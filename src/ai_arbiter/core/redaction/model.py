"""Types shared by detectors and redaction."""

from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict


class PIISpan(BaseModel):
    """Where something was found and what kind of thing it is. Never the text itself."""

    model_config = ConfigDict(frozen=True)

    category: str
    start: int
    end: int
    confidence: float


class DetectorInfo(BaseModel):
    """What a detector recognises and, as plainly, what it does not (ADR-0014)."""

    model_config = ConfigDict(frozen=True)

    category: str
    validates: str
    misses: str


class PIIDetector(Protocol):
    """Implemented by detector plugins, registered under ``ai_arbiter.pii_detectors``."""

    name: str

    def detect(self, text: str, *, locale: str | None = None) -> Sequence[PIISpan]: ...

    def describe(self) -> Sequence[DetectorInfo]: ...
