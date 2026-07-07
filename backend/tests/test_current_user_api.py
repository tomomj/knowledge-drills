import importlib
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, set_auth_client
from app.config import get_settings
from app.errors import AppError, register_exception_handlers
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.user_repository import UserRepository
from app.routes.users import router as users_router
from app.services.user_service import UserService


class StaticAuthClient:
    def __init__(self, user: AuthenticatedUser) -> None:
        self._user = user
        self.authorization_headers: list[str | None] = []

    def verify_authorization_header(self, authorization: str | None) -> AuthenticatedUser:
        self.authorization_headers.append(authorization)
        return self._user


class RejectingAuthClient:
    def verify_authorization_header(self, authorization: str | None) -> AuthenticatedUser:
        raise AppError("authentication_required", "Authentication is required.", status_code=401)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _clear_create_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "KNOWLEDGE_DRILLS_AGENT_MODE",
        "KNOWLEDGE_DRILLS_AGENT_TRACE_EXPORTER",
        "KNOWLEDGE_DRILLS_AUTH_MODE",
        "KNOWLEDGE_DRILLS_FIREBASE_PROJECT_ID",
        "KNOWLEDGE_DRILLS_LOCAL_AUTH_USER_ID",
        "KNOWLEDGE_DRILLS_LOCAL_AUTH_EMAIL",
        "KNOWLEDGE_DRILLS_STORAGE_MODE",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_user_service_creates_and_updates_profile_timestamps() -> None:
    repository = UserRepository(InMemoryFirestoreClient())
    times = iter(["2026-07-07T00:00:00+00:00", "2026-07-07T00:05:00+00:00"])
    service = UserService(repository, clock=lambda: next(times))

    created = service.upsert_current_user(
        AuthenticatedUser(
            uid="owner-1",
            email="before@example.test",
            display_name="Before",
            photo_url="https://example.test/before.png",
        )
    )
    updated = service.upsert_current_user(
        AuthenticatedUser(
            uid="owner-1",
            email="after@example.test",
            display_name="After",
            photo_url="https://example.test/after.png",
        )
    )

    assert created.created_at == "2026-07-07T00:00:00+00:00"
    assert updated.created_at == created.created_at
    assert updated.last_login_at == "2026-07-07T00:05:00+00:00"
    assert updated.email == "after@example.test"
    assert updated.display_name == "After"
    assert repository.get("owner-1") == updated


def test_me_route_upserts_profile_from_verified_user() -> None:
    firestore_client = InMemoryFirestoreClient()
    repository = UserRepository(firestore_client)
    auth_client = StaticAuthClient(
        AuthenticatedUser(
            uid="firebase-owner",
            email="owner@example.test",
            display_name="Course Owner",
            photo_url="https://example.test/owner.png",
        )
    )
    app = FastAPI()
    register_exception_handlers(app)
    set_auth_client(app, auth_client)
    app.state.user_service = UserService(
        repository,
        clock=lambda: "2026-07-07T00:00:00+00:00",
    )
    app.include_router(users_router)

    with TestClient(app) as client:
        response = client.get("/api/me", headers={"Authorization": "Bearer id-token"})

    assert response.status_code == 200
    assert response.json() == {
        "uid": "firebase-owner",
        "email": "owner@example.test",
        "displayName": "Course Owner",
        "photoUrl": "https://example.test/owner.png",
        "createdAt": "2026-07-07T00:00:00+00:00",
        "lastLoginAt": "2026-07-07T00:00:00+00:00",
    }
    assert auth_client.authorization_headers == ["Bearer id-token"]
    saved = repository.get("firebase-owner")
    assert saved is not None
    assert saved.uid == "firebase-owner"


def test_me_route_requires_verified_user_before_profile_upsert() -> None:
    repository = UserRepository(InMemoryFirestoreClient())
    app = FastAPI()
    register_exception_handlers(app)
    set_auth_client(app, RejectingAuthClient())
    app.state.user_service = UserService(repository)
    app.include_router(users_router)

    with TestClient(app) as client:
        response = client.get("/api/me")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert repository.get("firebase-owner") is None


def test_create_app_exposes_me_endpoint_in_local_auth_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_create_app_env(monkeypatch)
    monkeypatch.setenv("KNOWLEDGE_DRILLS_LOCAL_AUTH_USER_ID", "local-owner-2")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_LOCAL_AUTH_EMAIL", "local-owner-2@example.test")
    get_settings.cache_clear()

    app_main = importlib.import_module("app.main")
    app = app_main.create_app()

    with TestClient(app) as client:
        response = client.get("/api/me")

    assert response.status_code == 200
    assert response.json()["uid"] == "local-owner-2"
    assert response.json()["email"] == "local-owner-2@example.test"
    assert app.state.user_repository.get("local-owner-2") is not None
