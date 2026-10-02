import logging
import sys

import pytest

from ai_arbiter.core.config import LoggingSettings, TelemetrySettings
from ai_arbiter.core.errors import MissingExtraError
from ai_arbiter.core.telemetry import configure_logging, setup_telemetry


def test_disabled_telemetry_does_nothing() -> None:
    handle = setup_telemetry(TelemetrySettings(), service_version="1.2.3")

    assert handle.enabled is False
    handle.shutdown()


def test_enabled_telemetry_creates_a_provider_describing_the_service() -> None:
    pytest.importorskip("opentelemetry.sdk")
    settings = TelemetrySettings(enabled=True, service_name="arbiter-test")

    handle = setup_telemetry(settings, service_version="1.2.3")

    assert handle.enabled is True
    assert handle.provider is not None
    attributes = handle.provider.resource.attributes
    assert attributes["service.name"] == "arbiter-test"
    assert attributes["service.version"] == "1.2.3"
    handle.shutdown()


def test_exporter_is_attached_when_an_endpoint_is_configured() -> None:
    pytest.importorskip("opentelemetry.exporter.otlp.proto.http")
    settings = TelemetrySettings(enabled=True, otlp_endpoint="http://127.0.0.1:4318/")

    handle = setup_telemetry(settings, service_version="1.2.3")

    assert handle.enabled is True
    handle.shutdown()


def test_enabled_without_the_extra_says_which_extra_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A ``None`` entry in ``sys.modules`` makes the import fail as if it were not installed.
    monkeypatch.setitem(sys.modules, "opentelemetry.sdk.resources", None)

    with pytest.raises(MissingExtraError, match=r"ai-arbiter\[otel\]"):
        setup_telemetry(TelemetrySettings(enabled=True), service_version="1.2.3")


def test_logging_level_follows_settings() -> None:
    previous = logging.getLogger().level
    try:
        configure_logging(LoggingSettings(level="WARNING"))

        assert logging.getLogger().level == logging.WARNING
    finally:
        logging.basicConfig(level=previous, force=True)
