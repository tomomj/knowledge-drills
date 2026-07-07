from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from app.auth import AuthenticatedUser, require_current_user
from app.schemas import DocumentPatch, PatchDecisionRequest
from app.services.patch_service import PatchService

router = APIRouter(
    prefix="/api/patches",
    tags=["patches"],
    dependencies=[Depends(require_current_user)],
)


def get_patch_service(request: Request) -> PatchService:
    return cast(PatchService, request.app.state.patch_service)


@router.get("/{patch_id}", response_model=DocumentPatch)
def get_patch(
    request: Request,
    patch_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> DocumentPatch:
    return get_patch_service(request).get_patch(patch_id, current_user.uid)


@router.post("/{patch_id}/apply", response_model=DocumentPatch)
def apply_patch(
    request: Request,
    patch_id: str,
    payload: PatchDecisionRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> DocumentPatch:
    return get_patch_service(request).apply_patch(
        patch_id,
        owner_user_id=current_user.uid,
        owner_feedback=payload.owner_feedback,
    )


@router.post("/{patch_id}/reject", response_model=DocumentPatch)
def reject_patch(
    request: Request,
    patch_id: str,
    payload: PatchDecisionRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> DocumentPatch:
    return get_patch_service(request).reject_patch(
        patch_id,
        owner_user_id=current_user.uid,
        owner_feedback=payload.owner_feedback,
    )
