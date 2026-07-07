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
    assert settings.auth_mode == "none"
    assert settings.firebase_project_id is None
    assert settings.local_auth_user_id == "local-owner"
    assert settings.local_auth_email == "local-owner@example.test"
    assert settings.auth_configuration_error is None


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
    monkeypatch.setenv("KNOWLEDGE_DRILLS_AUTH_MODE", "firebase")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_FIREBASE_PROJECT_ID", "knowledge-drills-prd")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_LOCAL_AUTH_USER_ID", "dev-owner")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_LOCAL_AUTH_EMAIL", "dev-owner@example.test")

    settings = Settings()

    assert settings.storage_mode == "firestore"
    assert settings.firestore_database == "knowledge-drills-prd"
    assert settings.agent_mode == "adk"
    assert settings.agent_timeout_seconds == 120
    assert settings.agent_trace_exporter == "otlp"
    assert settings.agent_trace_service_name == "kd-api"
    assert settings.agent_trace_resource_attributes == "deployment.environment=test"
    assert settings.auth_mode == "firebase"
    assert settings.firebase_project_id == "knowledge-drills-prd"
    assert settings.local_auth_user_id == "dev-owner"
    assert settings.local_auth_email == "dev-owner@example.test"
    assert settings.auth_configuration_error is None


def test_firebase_auth_mode_detects_missing_project_id() -> None:
    settings = Settings(auth_mode="firebase")

    assert settings.auth_configuration_error == (
        "KNOWLEDGE_DRILLS_FIREBASE_PROJECT_ID is required when "
        "KNOWLEDGE_DRILLS_AUTH_MODE=firebase"
    )
