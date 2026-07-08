import logging
from typing import cast

from _pytest.logging import LogCaptureFixture
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.clients.agent_runtime_client import AgentInvocationError, AgentRuntimeClient
from app.errors import AppError
from app.main import create_app
from app.services.drill_service import DrillService
from app.services.share_token_service import ShareTokenService


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


def test_agent_invocation_error_returns_502_without_payload_and_app_continues(
    caplog: LogCaptureFixture,
) -> None:
    client = _client_with_test_routes()
    app = cast(FastAPI, client.app)
    sentinel = "SECRET_COURSE_BODY_d5f1"

    def failing_invoker(_task_name: str, _payload: dict[str, object]) -> dict[str, object]:
        raise AgentInvocationError(f"provider failed near {sentinel}")

    app.state.drill_service = DrillService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=app.state.drill_repository,
            share_token_repository=app.state.share_token_repository,
        ),
        agent_client=AgentRuntimeClient(invoker=failing_invoker),
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
    )
    course_response = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": sentinel},
    )
    course_id = course_response.json()["courseId"]

    with caplog.at_level(logging.ERROR, logger="app.error"):
        response = client.post(f"/api/courses/{course_id}/drill-runs")

    assert response.status_code == 502
    assert response.json()["code"] == "agent_invocation_failed"
    messages = [record.getMessage() for record in caplog.records]
    assert any("agent invocation failed" in message for message in messages)
    assert any("error_type=AgentInvocationError" in message for message in messages)
    assert all(record.levelno >= logging.ERROR for record in caplog.records)
    assert sentinel not in str(response.json())
    assert sentinel not in caplog.text

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"


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


def test_app_bootstrap_registers_local_auth_client_by_default() -> None:
    app: FastAPI = create_app()

    user = app.state.auth_client.verify_authorization_header(None)
    assert user.uid == "local-owner"


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
