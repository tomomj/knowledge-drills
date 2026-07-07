import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSettings:
    model: str
    project_id: str | None
    location: str


def get_agent_settings() -> AgentSettings:
    return AgentSettings(
        model=os.getenv("KNOWLEDGE_DRILL_AGENT_MODEL", "gemini-2.5-flash-lite"),
        project_id=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
