from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.clients.adk_agent_invoker import AdkAgentConfigurationError
from app.config import get_settings
from app.main import create_app
from app.repositories.firestore_client import InMemoryFirestoreClient


def _clear_auth_and_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "KNOWLEDGE_DRILLS_AGENT_MODE",
        "KNOWLEDGE_DRILLS_STORAGE_MODE",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_create_app_uses_local_invoker_by_default_without_google_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_auth_and_mode_env(monkeypatch)
    app = create_app()

    with TestClient(app) as client:
        course_response = client.post(
            "/api/courses",
            json={"title": "講座", "markdown": "# Body"},
        )
        course_id = course_response.json()["courseId"]

        response = client.post(f"/api/courses/{course_id}/drill-runs")

    assert response.status_code == 201
    assert response.json()["shareUrl"].startswith("/drills/")


def test_create_app_fails_fast_in_adk_mode_when_auth_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_auth_and_mode_env(monkeypatch)
    monkeypatch.setenv("KNOWLEDGE_DRILLS_AGENT_MODE", "adk")
    get_settings.cache_clear()

    with pytest.raises(AdkAgentConfigurationError, match="GOOGLE_API_KEY"):
        create_app()


def test_create_app_uses_firestore_client_in_firestore_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_auth_and_mode_env(monkeypatch)
    firestore_client = InMemoryFirestoreClient()
    monkeypatch.setenv("KNOWLEDGE_DRILLS_STORAGE_MODE", "firestore")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_FIRESTORE_DATABASE", "knowledge-drills-test")
    monkeypatch.setattr(
        "app.main.GoogleFirestoreClient",
        lambda database: firestore_client,
    )
    get_settings.cache_clear()

    app = create_app()

    assert app.state.firestore_client is firestore_client
