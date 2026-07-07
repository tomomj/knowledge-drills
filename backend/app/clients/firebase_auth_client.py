import logging
from collections.abc import Mapping
from typing import Any

import firebase_admin  # type: ignore[import-untyped]
from fastapi import status
from firebase_admin import auth

from app.auth import AuthClient, AuthenticatedUser
from app.config import Settings
from app.errors import AppError

logger = logging.getLogger("app.auth")

_FIREBASE_APP_NAME = "knowledge-drills"
_firebase_app: object | None = None
_firebase_project_id: str | None = None


class LocalAuthClient:
    def __init__(self, uid: str, email: str | None) -> None:
        self._user = AuthenticatedUser(uid=uid, email=email)

    def verify_authorization_header(self, authorization: str | None) -> AuthenticatedUser:
        return self._user


class MisconfiguredAuthClient:
    def __init__(self, reason: str) -> None:
        self._reason = reason

    def verify_authorization_header(self, authorization: str | None) -> AuthenticatedUser:
        logger.error("authentication client is misconfigured reason=%s", self._reason)
        raise AppError(
            "auth_not_configured",
            "Authentication is not configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class FirebaseAuthClient:
    def __init__(self, project_id: str) -> None:
        self._project_id = project_id

    def verify_authorization_header(self, authorization: str | None) -> AuthenticatedUser:
        token = _extract_bearer_token(authorization)
        app = _get_or_initialize_firebase_app(self._project_id)
        try:
            decoded_token = auth.verify_id_token(token, app=app)
        except Exception as exc:
            logger.info(
                "firebase token verification failed error_type=%s",
                type(exc).__name__,
            )
            raise AppError(
                "invalid_auth_token",
                "Invalid authentication token.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            ) from exc
        return _decode_authenticated_user(decoded_token)


def create_auth_client(settings: Settings) -> AuthClient:
    if settings.auth_mode == "firebase":
        if not settings.firebase_project_id:
            return MisconfiguredAuthClient(
                settings.auth_configuration_error or "firebase project id is required"
            )
        return FirebaseAuthClient(project_id=settings.firebase_project_id)
    return LocalAuthClient(
        uid=settings.local_auth_user_id,
        email=settings.local_auth_email,
    )


def _extract_bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise AppError(
            "authentication_required",
            "Authentication is required.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise AppError(
            "authentication_required",
            "Authentication is required.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return token


def _get_or_initialize_firebase_app(project_id: str) -> object:
    global _firebase_app, _firebase_project_id

    if _firebase_app is not None:
        if _firebase_project_id == project_id:
            return _firebase_app
        logger.error("firebase app project mismatch")
        raise _auth_not_configured()

    try:
        app = firebase_admin.get_app(name=_FIREBASE_APP_NAME)
    except ValueError:
        app = _initialize_firebase_app(project_id)
    except Exception as exc:
        logger.error("firebase app lookup failed error_type=%s", type(exc).__name__)
        raise _auth_not_configured() from exc
    else:
        existing_project_id = _firebase_app_project_id(app)
        if existing_project_id is not None and existing_project_id != project_id:
            logger.error("firebase app project mismatch")
            raise _auth_not_configured()

    _firebase_app = app
    _firebase_project_id = project_id
    return app


def _initialize_firebase_app(project_id: str) -> object:
    try:
        return firebase_admin.initialize_app(
            options={"projectId": project_id},
            name=_FIREBASE_APP_NAME,
        )
    except Exception as exc:
        logger.error("firebase app initialization failed error_type=%s", type(exc).__name__)
        raise _auth_not_configured() from exc


def _auth_not_configured() -> AppError:
    return AppError(
        "auth_not_configured",
        "Authentication is not configured.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def _decode_authenticated_user(decoded_token: Mapping[str, Any]) -> AuthenticatedUser:
    uid = _string_claim(decoded_token, "uid") or _string_claim(decoded_token, "sub")
    if uid is None:
        raise AppError(
            "invalid_auth_token",
            "Invalid authentication token.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return AuthenticatedUser(
        uid=uid,
        email=_string_claim(decoded_token, "email"),
        display_name=_string_claim(decoded_token, "name"),
        photo_url=_string_claim(decoded_token, "picture"),
    )


def _string_claim(decoded_token: Mapping[str, Any], claim: str) -> str | None:
    value = decoded_token.get(claim)
    if isinstance(value, str) and value:
        return value
    return None


def _firebase_app_project_id(app: object) -> str | None:
    options = getattr(app, "options", None)
    if isinstance(options, Mapping):
        project_id = options.get("projectId")
        if isinstance(project_id, str) and project_id:
            return project_id
    get_option = getattr(options, "get", None)
    if callable(get_option):
        project_id = get_option("projectId")
        if isinstance(project_id, str) and project_id:
            return project_id
    return None
