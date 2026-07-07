import importlib
import logging
from collections.abc import Callable
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, require_current_user, set_auth_client
from app.clients import firebase_auth_client
from app.clients.firebase_auth_client import (
    FirebaseAuthClient,
    LocalAuthClient,
    MisconfiguredAuthClient,
    create_auth_client,
)
from app.config import Settings, get_settings
from app.errors import AppError, register_exception_handlers


@pytest.fixture(autouse=True)
def reset_firebase_auth_client_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(firebase_auth_client, "_firebase_app", None)
    monkeypatch.setattr(firebase_auth_client, "_firebase_project_id", None)


def _assert_app_error(exc: AppError, code: str, status_code: int) -> None:
    assert exc.code == code
    assert exc.status_code == status_code


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


def test_local_auth_client_accepts_missing_authorization_header() -> None:
    client = create_auth_client(
        Settings(
            auth_mode="none",
            local_auth_user_id="local-user-1",
            local_auth_email="local-user@example.test",
        )
    )

    user = client.verify_authorization_header(None)

    assert isinstance(client, LocalAuthClient)
    assert user == AuthenticatedUser(
        uid="local-user-1",
        email="local-user@example.test",
    )


def test_create_app_registers_auth_client_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_create_app_env(monkeypatch)
    monkeypatch.setenv("KNOWLEDGE_DRILLS_LOCAL_AUTH_USER_ID", "wired-local-owner")
    monkeypatch.setenv("KNOWLEDGE_DRILLS_LOCAL_AUTH_EMAIL", "wired-owner@example.test")
    get_settings.cache_clear()

    try:
        app_main = importlib.import_module("app.main")
        app = app_main.create_app()
    finally:
        get_settings.cache_clear()

    user = app.state.auth_client.verify_authorization_header(None)
    assert user == AuthenticatedUser(
        uid="wired-local-owner",
        email="wired-owner@example.test",
    )


def test_misconfigured_auth_client_maps_to_500_and_logs_without_secret(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = MisconfiguredAuthClient("firebase project id is required")

    with (
        caplog.at_level(logging.ERROR, logger="app.auth"),
        pytest.raises(AppError) as exc_info,
    ):
        client.verify_authorization_header("Bearer secret-id-token")

    _assert_app_error(exc_info.value, "auth_not_configured", 500)
    assert "firebase project id is required" in caplog.text
    assert "secret-id-token" not in caplog.text


def test_create_auth_client_returns_misconfigured_client_for_firebase_without_project() -> None:
    client = create_auth_client(Settings(auth_mode="firebase", firebase_project_id=None))

    assert isinstance(client, MisconfiguredAuthClient)
    with pytest.raises(AppError) as exc_info:
        client.verify_authorization_header(None)
    _assert_app_error(exc_info.value, "auth_not_configured", 500)


@pytest.mark.parametrize("authorization", [None, "", "token abc", "Bearer", "Bearer "])
def test_firebase_auth_client_requires_bearer_authorization_header(
    authorization: str | None,
) -> None:
    client = FirebaseAuthClient(project_id="test-project")

    with pytest.raises(AppError) as exc_info:
        client.verify_authorization_header(authorization)

    _assert_app_error(exc_info.value, "authentication_required", 401)


def test_firebase_auth_client_decodes_verified_token_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = object()
    calls: list[tuple[str, dict[str, str]]] = []
    verified: list[tuple[str, object]] = []

    def fake_get_app(name: str) -> object:
        raise ValueError("missing app")

    def fake_initialize_app(*, options: dict[str, str], name: str) -> object:
        calls.append((name, options))
        return app

    def fake_verify_id_token(token: str, app: object) -> dict[str, object]:
        verified.append((token, app))
        return {
            "uid": "firebase-user-1",
            "email": "owner@example.test",
            "name": "Course Owner",
            "picture": "https://example.test/owner.png",
        }

    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.get_app",
        fake_get_app,
    )
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.initialize_app",
        fake_initialize_app,
    )
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.auth.verify_id_token",
        fake_verify_id_token,
    )

    user = FirebaseAuthClient(project_id="test-project").verify_authorization_header(
        "Bearer firebase-id-token"
    )

    assert user == AuthenticatedUser(
        uid="firebase-user-1",
        email="owner@example.test",
        display_name="Course Owner",
        photo_url="https://example.test/owner.png",
    )
    assert calls == [("knowledge-drills", {"projectId": "test-project"})]
    assert verified == [("firebase-id-token", app)]


def test_firebase_auth_client_reuses_singleton_for_same_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = object()
    initialize_calls = 0

    def fake_get_app(name: str) -> object:
        raise ValueError("missing app")

    def fake_initialize_app(*, options: dict[str, str], name: str) -> object:
        nonlocal initialize_calls
        initialize_calls += 1
        return app

    def fake_verify_id_token(token: str, app: object) -> dict[str, object]:
        return {"uid": token.removeprefix("token-")}

    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.get_app",
        fake_get_app,
    )
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.initialize_app",
        fake_initialize_app,
    )
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.auth.verify_id_token",
        fake_verify_id_token,
    )

    first = FirebaseAuthClient(project_id="test-project").verify_authorization_header(
        "Bearer token-one"
    )
    second = FirebaseAuthClient(project_id="test-project").verify_authorization_header(
        "Bearer token-two"
    )

    assert first.uid == "one"
    assert second.uid == "two"
    assert initialize_calls == 1


def test_firebase_auth_client_rejects_different_project_after_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = object()

    def fake_get_app(name: str) -> object:
        raise ValueError("missing app")

    def fake_initialize_app(*, options: dict[str, str], name: str) -> object:
        return app

    def fake_verify_id_token(token: str, app: object) -> dict[str, object]:
        return {"uid": "owner"}

    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.get_app",
        fake_get_app,
    )
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.initialize_app",
        fake_initialize_app,
    )
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.auth.verify_id_token",
        fake_verify_id_token,
    )

    FirebaseAuthClient(project_id="first-project").verify_authorization_header("Bearer token")

    with pytest.raises(AppError) as exc_info:
        FirebaseAuthClient(project_id="second-project").verify_authorization_header("Bearer token")

    _assert_app_error(exc_info.value, "auth_not_configured", 500)


@pytest.mark.parametrize(
    "decoded_token",
    [
        {},
        {"uid": ""},
        {"sub": ""},
    ],
)
def test_firebase_auth_client_requires_uid_or_sub_in_decoded_token(
    monkeypatch: pytest.MonkeyPatch,
    decoded_token: dict[str, object],
) -> None:
    _patch_successful_firebase_app(monkeypatch)
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.auth.verify_id_token",
        lambda token, app: decoded_token,
    )

    with pytest.raises(AppError) as exc_info:
        FirebaseAuthClient(project_id="test-project").verify_authorization_header("Bearer token")

    _assert_app_error(exc_info.value, "invalid_auth_token", 401)


@pytest.mark.parametrize(
    "exception_factory",
    [
        lambda: type("ExpiredIdTokenError", (Exception,), {})("expired"),
        lambda: type("InvalidIdTokenError", (Exception,), {})("invalid"),
        lambda: ValueError("certificate fetch failed"),
    ],
)
def test_firebase_auth_client_maps_verification_errors_to_401_without_logging_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    exception_factory: Callable[[], Exception],
) -> None:
    _patch_successful_firebase_app(monkeypatch)

    def fake_verify_id_token(token: str, app: object) -> dict[str, object]:
        raise exception_factory()

    monkeypatch.setattr(
        "app.clients.firebase_auth_client.auth.verify_id_token",
        fake_verify_id_token,
    )

    with (
        caplog.at_level(logging.INFO, logger="app.auth"),
        pytest.raises(AppError) as exc_info,
    ):
        FirebaseAuthClient(project_id="test-project").verify_authorization_header(
            "Bearer sensitive-id-token"
        )

    _assert_app_error(exc_info.value, "invalid_auth_token", 401)
    assert "sensitive-id-token" not in caplog.text
    assert any(
        error_type in caplog.text
        for error_type in ("ExpiredIdTokenError", "InvalidIdTokenError", "ValueError")
    )


def test_firebase_auth_client_maps_initialization_error_to_500(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def fake_get_app(name: str) -> object:
        raise ValueError("missing app")

    def fake_initialize_app(*, options: dict[str, str], name: str) -> object:
        raise RuntimeError("adc unavailable")

    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.get_app",
        fake_get_app,
    )
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.initialize_app",
        fake_initialize_app,
    )

    with (
        caplog.at_level(logging.ERROR, logger="app.auth"),
        pytest.raises(AppError) as exc_info,
    ):
        FirebaseAuthClient(project_id="test-project").verify_authorization_header(
            "Bearer token"
        )

    _assert_app_error(exc_info.value, "auth_not_configured", 500)
    assert "RuntimeError" in caplog.text
    assert "Bearer token" not in caplog.text


def test_require_current_user_dependency_returns_verified_user() -> None:
    class StaticAuthClient:
        def verify_authorization_header(self, authorization: str | None) -> AuthenticatedUser:
            assert authorization == "Bearer verified-token"
            return AuthenticatedUser(uid="verified-user")

    app = FastAPI()
    register_exception_handlers(app)
    set_auth_client(app, StaticAuthClient())

    @app.get("/protected")
    def protected(
        current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    ) -> dict[str, str]:
        return {"uid": current_user.uid}

    with TestClient(app) as client:
        response = client.get("/protected", headers={"Authorization": "Bearer verified-token"})

    assert response.status_code == 200
    assert response.json() == {"uid": "verified-user"}


def _patch_successful_firebase_app(monkeypatch: pytest.MonkeyPatch) -> object:
    app = object()
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.get_app",
        lambda name: app,
    )
    monkeypatch.setattr(
        "app.clients.firebase_auth_client.firebase_admin.initialize_app",
        lambda *, options, name: app,
    )
    return app
