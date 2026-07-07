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


@lru_cache
def get_settings() -> Settings:
    return Settings()
