from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from app.auth import AuthenticatedUser, require_current_user
from app.schemas import CurrentUserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/api", tags=["users"])


def get_user_service(request: Request) -> UserService:
    return cast(UserService, request.app.state.user_service)


@router.get("/me", response_model=CurrentUserResponse)
def get_current_user(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> CurrentUserResponse:
    profile = get_user_service(request).upsert_current_user(current_user)
    return CurrentUserResponse.model_validate(profile.model_dump())
