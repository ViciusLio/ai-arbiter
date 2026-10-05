"""Load the detector of personal data named in the configuration (ADR-0011)."""

from ai_arbiter.core.config.settings import Settings
from ai_arbiter.core.errors import ConfigurationError
from ai_arbiter.core.plugins.registry import PII_DETECTORS, PluginRegistry
from ai_arbiter.core.redaction.model import PIIDetector


def load_detector(registry: PluginRegistry, settings: Settings) -> PIIDetector:
    """The detector ``plugins.pii_detector`` with ``redaction.detector_settings``.

    Raises ``PluginError`` for an unknown detector and ``ConfigurationError`` for
    settings it does not take.
    """
    name = settings.plugins.pii_detector
    plugin = registry.load(PII_DETECTORS, name)
    try:
        detector: PIIDetector = plugin(**settings.redaction.detector_settings)
    except TypeError as exc:
        raise ConfigurationError(
            f"redaction.detector_settings: the detector '{name}' does not take these settings"
        ) from exc
    return detector
