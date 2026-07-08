import pytest

from knowledge_drill_agent.config import get_agent_settings


def test_agent_analysis_mode_defaults_to_composed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE", raising=False)

    settings = get_agent_settings()

    assert settings.analysis_mode == "composed"


def test_agent_analysis_mode_accepts_single_and_composed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE", "single")
    assert get_agent_settings().analysis_mode == "single"

    monkeypatch.setenv("KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE", "composed")
    assert get_agent_settings().analysis_mode == "composed"


def test_agent_analysis_mode_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE", "parallel")

    with pytest.raises(ValueError, match="KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE"):
        get_agent_settings()
