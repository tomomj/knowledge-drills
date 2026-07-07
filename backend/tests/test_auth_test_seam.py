from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, require_current_user, set_auth_client
from app.errors import AppError, register_exception_handlers


class FakeAuthClient:
    def __init__(
        self,
        user: AuthenticatedUser | None = None,
        error: AppError | None = None,
    ) -> None:
        self._user = user or AuthenticatedUser(
            uid="fake-owner",
            email="fake-owner@example.test",
            display_name="Fake Owner",
            photo_url="https://example.test/avatar.png",
        )
        self._error = error
        self.authorization_headers: list[str | None] = []

    def verify_authorization_header(self, authorization: str | None) -> AuthenticatedUser:
        self.authorization_headers.append(authorization)
        if self._error is not None:
            raise self._error
        return self._user


def _create_test_app(fake_auth_client: FakeAuthClient | None = None) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/protected")
    def protected(
        current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    ) -> dict[str, str | None]:
        return {
            "uid": current_user.uid,
            "email": current_user.email,
            "displayName": current_user.display_name,
            "photoUrl": current_user.photo_url,
        }

    if fake_auth_client is not None:
        set_auth_client(app, fake_auth_client)
    return app


def test_route_tests_can_inject_fake_auth_client_without_firebase() -> None:
    fake_auth_client = FakeAuthClient()

    with TestClient(_create_test_app(fake_auth_client)) as client:
        response = client.get("/protected", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    assert response.json() == {
        "uid": "fake-owner",
        "email": "fake-owner@example.test",
        "displayName": "Fake Owner",
        "photoUrl": "https://example.test/avatar.png",
    }
    assert fake_auth_client.authorization_headers == ["Bearer test-token"]


def test_fake_auth_client_can_drive_auth_error_responses_without_firebase() -> None:
    fake_auth_client = FakeAuthClient(
        error=AppError(
            "invalid_auth_token",
            "Invalid authentication token.",
            status_code=401,
        )
    )

    with TestClient(_create_test_app(fake_auth_client)) as client:
        response = client.get("/protected", headers={"Authorization": "Bearer bad-token"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_auth_token"
    assert fake_auth_client.authorization_headers == ["Bearer bad-token"]


def test_missing_auth_client_is_reported_as_configuration_error() -> None:
    with TestClient(_create_test_app()) as client:
        response = client.get("/protected")

    assert response.status_code == 500
    assert response.json()["code"] == "auth_not_configured"
