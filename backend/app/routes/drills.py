from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from app.auth import AuthenticatedUser, require_current_user
from app.schemas import DocumentPatch, DrillAdminResponse
from app.services.analysis_service import AnalysisService
from app.services.drill_service import DrillService

router = APIRouter(
    prefix="/api/drill-runs",
    tags=["drills"],
    dependencies=[Depends(require_current_user)],
)


def get_drill_service(request: Request) -> DrillService:
    return cast(DrillService, request.app.state.drill_service)


def get_analysis_service(request: Request) -> AnalysisService:
    return cast(AnalysisService, request.app.state.analysis_service)


@router.get("/{drill_run_id}", response_model=DrillAdminResponse)
async def get_drill_admin(
    request: Request,
    drill_run_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> DrillAdminResponse:
    return get_drill_service(request).get_admin_drill(
        drill_run_id,
        owner_user_id=current_user.uid,
    )


@router.post("/{drill_run_id}/analysis", response_model=DocumentPatch)
def analyze_drill(
    request: Request,
    drill_run_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> DocumentPatch:
    return get_analysis_service(request).run_analysis(drill_run_id, current_user.uid)
