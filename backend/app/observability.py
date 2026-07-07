import logging
import os

from google.adk.telemetry.google_cloud import get_gcp_exporters
from google.adk.telemetry.setup import maybe_set_otel_providers

from app.config import Settings

logger = logging.getLogger("app.observability")

_OTLP_TRACE_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
_OTLP_ENDPOINT_ENV = "OTEL_EXPORTER_OTLP_ENDPOINT"


class AdkTelemetryConfigurationError(RuntimeError):
    """Raised when ADK trace export is enabled without required configuration."""


def configure_adk_tracing(settings: Settings) -> None:
    """Configure ADK OpenTelemetry export for the backend process."""
    if settings.agent_mode != "adk" or settings.agent_trace_exporter == "none":
        return

    _set_default_otel_resource_env(settings)

    if settings.agent_trace_exporter == "otlp":
        _configure_otlp_export()
        return

    gcp_exporters = get_gcp_exporters(enable_cloud_tracing=True)
    maybe_set_otel_providers([gcp_exporters])
    logger.info("adk trace export configured exporter=gcp")


def _configure_otlp_export() -> None:
    if not os.environ.get(_OTLP_TRACE_ENDPOINT_ENV) and not os.environ.get(_OTLP_ENDPOINT_ENV):
        raise AdkTelemetryConfigurationError(
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT or OTEL_EXPORTER_OTLP_ENDPOINT "
            "is required when KNOWLEDGE_DRILLS_AGENT_TRACE_EXPORTER=otlp"
        )
    maybe_set_otel_providers()
    logger.info("adk trace export configured exporter=otlp")


def _set_default_otel_resource_env(settings: Settings) -> None:
    os.environ.setdefault("OTEL_SERVICE_NAME", settings.agent_trace_service_name)
    if settings.agent_trace_resource_attributes:
        os.environ.setdefault(
            "OTEL_RESOURCE_ATTRIBUTES",
            settings.agent_trace_resource_attributes,
        )
