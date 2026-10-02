"""Logging and OpenTelemetry bootstrap.

Telemetry is off by default. When enabled it needs the ``otel`` extra; spans carry
identifiers and counts, never prompt or completion content.
"""

import logging
from dataclasses import dataclass
from typing import Any

from ai_arbiter.core.config.settings import LoggingSettings, TelemetrySettings
from ai_arbiter.core.errors import MissingExtraError

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(settings: LoggingSettings) -> None:
    logging.basicConfig(level=settings.level, format=LOG_FORMAT, force=True)
    # Alembic announces itself at INFO each time the schema revision is read, which the
    # readiness probe does on every call.
    logging.getLogger("alembic.runtime.migration").setLevel(logging.WARNING)


@dataclass
class TelemetryHandle:
    """Returned by ``setup_telemetry``; call ``shutdown`` when the process stops."""

    provider: Any | None = None

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    def shutdown(self) -> None:
        if self.provider is not None:
            self.provider.shutdown()


def setup_telemetry(settings: TelemetrySettings, *, service_version: str) -> TelemetryHandle:
    """Create the tracer provider, or do nothing if telemetry is disabled.

    The provider is returned, not installed globally: the caller decides where it is
    used. Raises ``MissingExtraError`` if telemetry is enabled without the ``otel`` extra.
    """
    if not settings.enabled:
        return TelemetryHandle()
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        raise MissingExtraError("otel", "Telemetry") from exc

    resource = Resource.create(
        {"service.name": settings.service_name, "service.version": service_version}
    )
    provider = TracerProvider(resource=resource)
    if settings.otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = settings.otlp_endpoint.rstrip("/") + "/v1/traces"
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    return TelemetryHandle(provider=provider)
