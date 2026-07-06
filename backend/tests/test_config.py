import pytest

from app.config import Settings


def test_agent_settings_defaults() -> None:
    settings = Settings()

    assert settings.agent_mode == "local"
    assert settings.agent_timeout_seconds == 60


def test_agent_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_DRILLS_AGENT_MODE", "adk")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS", "120")

    settings = Settings()

    assert settings.agent_mode == "adk"
    assert settings.agent_timeout_seconds == 120
