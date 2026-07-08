import os
from dataclasses import dataclass
from typing import Literal, cast

AnalysisMode = Literal["single", "composed"]


@dataclass(frozen=True)
class AgentSettings:
    model: str
    project_id: str | None
    location: str
    analysis_mode: AnalysisMode


def _resolve_analysis_mode(value: str | None) -> AnalysisMode:
    mode = value or "composed"
    if mode not in ("single", "composed"):
        raise ValueError(
            "KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE must be either 'single' or 'composed'"
        )
    return cast(AnalysisMode, mode)


def get_agent_settings() -> AgentSettings:
    return AgentSettings(
        model=os.getenv("KNOWLEDGE_DRILL_AGENT_MODEL", "gemini-2.5-flash-lite"),
        project_id=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        analysis_mode=_resolve_analysis_mode(os.getenv("KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE")),
    )
