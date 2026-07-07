import os

import pytest

from app.config import Settings
from app.observability import AdkTelemetryConfigurationError, configure_adk_tracing


def test_configure_adk_tracing_skips_when_disabled_or_not_adk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_maybe_set_otel_providers(
        otel_hooks_to_setup: object | None = None,
        otel_resource: object | None = None,
    ) -> None:
        raise AssertionError("ADK tracing should not be configured")

    monkeypatch.setattr(
        "app.observability.maybe_set_otel_providers",
        fail_maybe_set_otel_providers,
    )

    configure_adk_tracing(Settings(agent_mode="adk", agent_trace_exporter="none"))
    configure_adk_tracing(Settings(agent_mode="local", agent_trace_exporter="otlp"))


def test_configure_adk_tracing_otlp_requires_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    with pytest.raises(AdkTelemetryConfigurationError, match="OTEL_EXPORTER_OTLP"):
        configure_adk_tracing(Settings(agent_mode="adk", agent_trace_exporter="otlp"))


def test_configure_adk_tracing_otlp_sets_default_resource_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object | None] = []

    def fake_maybe_set_otel_providers(
        otel_hooks_to_setup: object | None = None,
        otel_resource: object | None = None,
    ) -> None:
        calls.append(otel_hooks_to_setup)

    monkeypatch.setattr(
        "app.observability.maybe_set_otel_providers",
        fake_maybe_set_otel_providers,
    )
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "http://otel-collector:4318/v1/traces",
    )
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)

    configure_adk_tracing(
        Settings(
            agent_mode="adk",
            agent_trace_exporter="otlp",
            agent_trace_service_name="kd-api",
            agent_trace_resource_attributes="deployment.environment=test",
        )
    )

    assert calls == [None]
    assert os.environ["OTEL_SERVICE_NAME"] == "kd-api"
    assert os.environ["OTEL_RESOURCE_ATTRIBUTES"] == "deployment.environment=test"


def test_configure_adk_tracing_gcp_uses_cloud_trace_exporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gcp_hooks = object()
    get_calls: list[bool] = []
    maybe_calls: list[object | None] = []

    def fake_get_gcp_exporters(
        *,
        enable_cloud_tracing: bool = False,
        enable_cloud_metrics: bool = False,
        enable_cloud_logging: bool = False,
        google_auth: object | None = None,
    ) -> object:
        get_calls.append(enable_cloud_tracing)
        assert enable_cloud_metrics is False
        assert enable_cloud_logging is False
        assert google_auth is None
        return gcp_hooks

    def fake_maybe_set_otel_providers(
        otel_hooks_to_setup: object | None = None,
        otel_resource: object | None = None,
    ) -> None:
        maybe_calls.append(otel_hooks_to_setup)

    monkeypatch.setattr("app.observability.get_gcp_exporters", fake_get_gcp_exporters)
    monkeypatch.setattr(
        "app.observability.maybe_set_otel_providers",
        fake_maybe_set_otel_providers,
    )

    configure_adk_tracing(Settings(agent_mode="adk", agent_trace_exporter="gcp"))

    assert get_calls == [True]
    assert maybe_calls == [[gcp_hooks]]
