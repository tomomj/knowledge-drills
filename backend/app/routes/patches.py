from typing import cast

from fastapi import APIRouter, Request

from app.schemas import DocumentPatch, PatchDecisionRequest
from app.services.patch_service import PatchService

router = APIRouter(prefix="/api/patches", tags=["patches"])


def get_patch_service(request: Request) -> PatchService:
    return cast(PatchService, request.app.state.patch_service)


@router.get("/{patch_id}", response_model=DocumentPatch)
def get_patch(request: Request, patch_id: str) -> DocumentPatch:
    return get_patch_service(request).get_patch(patch_id)


@router.post("/{patch_id}/apply", response_model=DocumentPatch)
def apply_patch(
    request: Request,
    patch_id: str,
    payload: PatchDecisionRequest,
) -> DocumentPatch:
    return get_patch_service(request).apply_patch(
        patch_id,
        owner_feedback=payload.owner_feedback,
    )


@router.post("/{patch_id}/reject", response_model=DocumentPatch)
def reject_patch(
    request: Request,
    patch_id: str,
    payload: PatchDecisionRequest,
) -> DocumentPatch:
    return get_patch_service(request).reject_patch(
        patch_id,
        owner_feedback=payload.owner_feedback,
    )
