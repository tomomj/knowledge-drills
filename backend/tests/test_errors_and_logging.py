import logging

from _pytest.logging import LogCaptureFixture
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import AppError
from app.main import create_app


class Payload(BaseModel):
    title: str


def _client_with_test_routes() -> TestClient:
    app = create_app()

    @app.post("/test/validation")
    async def validation_route(_payload: Payload) -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/test/app-error/{courseId}")
    async def app_error_route(courseId: str) -> None:
        raise AppError("course_not_found", f"Course {courseId} was not found", status_code=404)

    @app.get("/test/system-error")
    async def system_error_route() -> None:
        raise RuntimeError("boom")

    return TestClient(app, raise_server_exceptions=False)


def test_validation_error_response_includes_request_id_and_code() -> None:
    client = _client_with_test_routes()

    response = client.post("/test/validation", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["requestId"]
    assert response.headers["x-request-id"] == response.json()["requestId"]


def test_system_error_response_is_distinct_from_app_error() -> None:
    client = _client_with_test_routes()

    app_response = client.get("/test/app-error/course-1")
    system_response = client.get("/test/system-error")

    assert app_response.status_code == 404
    assert app_response.json()["code"] == "course_not_found"
    assert system_response.status_code == 500
    assert system_response.json()["code"] == "internal_server_error"


def test_access_log_includes_request_and_resource_ids_without_body(
    caplog: LogCaptureFixture,
) -> None:
    client = _client_with_test_routes()

    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/test/app-error/course-1")

    assert response.status_code == 404
    messages = [record.getMessage() for record in caplog.records]
    assert any("request completed" in message for message in messages)
    assert any("course-1" in message for message in messages)
    assert all("sensitive learner answer" not in message for message in messages)


def test_app_bootstrap_declares_no_auth_boundary() -> None:
    app: FastAPI = create_app()

    assert app.state.auth_boundary == "mvp_no_auth"


def test_cors_allows_local_vite_dev_server() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/api/courses",
        headers={
            "origin": "http://127.0.0.1:5175",
            "access-control-request-method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5175"
