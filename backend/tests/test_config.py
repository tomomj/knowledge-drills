import pytest

from app.config import Settings


def test_agent_settings_defaults() -> None:
    settings = Settings()

    assert settings.storage_mode == "memory"
    assert settings.firestore_database == "(default)"
    assert settings.agent_mode == "local"
    assert settings.agent_timeout_seconds == 60
    assert settings.agent_trace_exporter == "none"
    assert settings.agent_trace_service_name == "knowledge-drills-backend"
    assert settings.agent_trace_resource_attributes == ""


def test_agent_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_DRILLS_STORAGE_MODE", "firestore")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_FIRESTORE_DATABASE", "knowledge-drills-prd")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_AGENT_MODE", "adk")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_AGENT_TRACE_EXPORTER", "otlp")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_AGENT_TRACE_SERVICE_NAME", "kd-api")
    monkeypatch.setenv(
        "KNOWLEDGE_DRILLS_AGENT_TRACE_RESOURCE_ATTRIBUTES",
        "deployment.environment=test",
    )

    settings = Settings()

    assert settings.storage_mode == "firestore"
    assert settings.firestore_database == "knowledge-drills-prd"
    assert settings.agent_mode == "adk"
    assert settings.agent_timeout_seconds == 120
    assert settings.agent_trace_exporter == "otlp"
    assert settings.agent_trace_service_name == "kd-api"
    assert settings.agent_trace_resource_attributes == "deployment.environment=test"
