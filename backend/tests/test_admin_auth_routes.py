from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, set_auth_client
from app.config import get_settings
from app.errors import AppError
from app.main import create_app


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


@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("get", "/api/courses", None),
        ("post", "/api/courses", {"title": "講座", "markdown": "# Body"}),
        ("get", "/api/courses/course-1", None),
        ("put", "/api/courses/course-1", {"title": "講座", "markdown": "# Body"}),
        ("get", "/api/courses/course-1/revisions", None),
        ("get", "/api/courses/course-1/revisions/diff?from=1&to=2", None),
        ("post", "/api/courses/course-1/drill-runs", None),
        ("get", "/api/courses/course-1/drill-runs/drill-1", None),
        ("get", "/api/courses/course-1/drill-runs/drill-1/answers", None),
        ("post", "/api/courses/course-1/drill-runs/drill-1/analyze", None),
        ("get", "/api/drill-runs/drill-1", None),
        ("post", "/api/drill-runs/drill-1/analysis", None),
        ("get", "/api/patches/patch-1", None),
        ("post", "/api/patches/patch-1/apply", {"ownerFeedback": "反映"}),
        ("post", "/api/patches/patch-1/reject", {"ownerFeedback": "却下"}),
    ],
)
def test_admin_routes_require_current_user(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    json_body: dict[str, object] | None,
) -> None:
    _clear_create_app_env(monkeypatch)
    app = create_app()
    set_auth_client(app, RejectingAuthClient())

    with TestClient(app) as client:
        request = getattr(client, method)
        response = request(path, json=json_body) if json_body is not None else request(path)

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_admin_routes_allow_local_auth_mode_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_create_app_env(monkeypatch)
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/api/courses")

    assert response.status_code == 200
    assert response.json() == {"courses": []}


@pytest.mark.parametrize(
    ("method", "path", "json_body", "expected_status"),
    [
        ("get", "/health", None, 200),
        ("get", "/api/drills/missing-token", None, 404),
        ("get", "/api/learn/missing-token", None, 404),
        (
            "post",
            "/api/drills/missing-token/answers",
            {"learnerName": "受講者", "answers": []},
            404,
        ),
        (
            "post",
            "/api/learn/missing-token/answers",
            {"learnerName": "受講者", "answers": []},
            404,
        ),
    ],
)
def test_public_routes_do_not_require_current_user(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    json_body: dict[str, object] | None,
    expected_status: int,
) -> None:
    _clear_create_app_env(monkeypatch)
    app = create_app()
    set_auth_client(app, RejectingAuthClient())

    with TestClient(app) as client:
        request = getattr(client, method)
        response = request(path, json=json_body) if json_body is not None else request(path)

    assert response.status_code == expected_status
    if expected_status == 404:
        assert response.json()["code"] == "invalid_share_token"
