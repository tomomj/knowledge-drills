from typing import Protocol, cast

from fastapi import FastAPI, Request, status

from app.errors import AppError
from app.schemas import ApiModel


class AuthenticatedUser(ApiModel):
    uid: str
    email: str | None = None
    display_name: str | None = None
    photo_url: str | None = None


class AuthClient(Protocol):
    def verify_authorization_header(self, authorization: str | None) -> AuthenticatedUser:
        """Return the authenticated user or raise AppError for auth failures."""
        ...


def set_auth_client(app: FastAPI, auth_client: AuthClient) -> None:
    app.state.auth_client = auth_client


def get_auth_client(request: Request) -> AuthClient:
    auth_client = getattr(request.app.state, "auth_client", None)
    if auth_client is None:
        raise AppError(
            "auth_not_configured",
            "Authentication client is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return cast(AuthClient, auth_client)


def require_current_user(request: Request) -> AuthenticatedUser:
    auth_client = get_auth_client(request)
    return auth_client.verify_authorization_header(request.headers.get("authorization"))
