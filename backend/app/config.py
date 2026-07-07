from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Knowledge Drills API"
    environment: str = "dev"
    storage_mode: Literal["memory", "firestore"] = "memory"
    firestore_database: str = "(default)"
    agent_mode: str = "local"
    agent_timeout_seconds: int = 60
    agent_trace_exporter: Literal["none", "otlp", "gcp"] = "none"
    agent_trace_service_name: str = "knowledge-drills-backend"
    agent_trace_resource_attributes: str = ""
    auth_mode: Literal["none", "firebase"] = "none"
    firebase_project_id: str | None = None
    local_auth_user_id: str = "local-owner"
    local_auth_email: str = "local-owner@example.test"
    cors_allowed_origins: str = (
        "http://127.0.0.1:5173,"
        "http://127.0.0.1:5174,"
        "http://127.0.0.1:5175,"
        "http://localhost:5173,"
        "http://localhost:5174,"
        "http://localhost:5175"
    )

    model_config = SettingsConfigDict(env_file=".env", env_prefix="KNOWLEDGE_DRILLS_")

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def auth_configuration_error(self) -> str | None:
        if self.auth_mode == "firebase" and not self.firebase_project_id:
            return (
                "KNOWLEDGE_DRILLS_FIREBASE_PROJECT_ID is required when "
                "KNOWLEDGE_DRILLS_AUTH_MODE=firebase"
            )
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
