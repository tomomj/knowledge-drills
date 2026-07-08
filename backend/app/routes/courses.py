from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request, status

from app.auth import AuthenticatedUser, require_current_user
from app.schemas import (
    AnalysisStartResponse,
    CourseCreateRequest,
    CourseCreateResponse,
    CourseDetailResponse,
    CourseListResponse,
    CourseMetricsResponse,
    CourseRevisionDiffResponse,
    CourseRevisionListResponse,
    CourseUpdateRequest,
    DrillAdminResponse,
    DrillAnswersResponse,
    DrillGenerationStartResponse,
)
from app.services.analysis_service import AnalysisService
from app.services.course_service import CourseService
from app.services.drill_service import DrillService

router = APIRouter(
    prefix="/api/courses",
    tags=["courses"],
    dependencies=[Depends(require_current_user)],
)


def get_course_service(request: Request) -> CourseService:
    return cast(CourseService, request.app.state.course_service)


def get_drill_service(request: Request) -> DrillService:
    return cast(DrillService, request.app.state.drill_service)


def get_analysis_service(request: Request) -> AnalysisService:
    return cast(AnalysisService, request.app.state.analysis_service)


@router.post("", response_model=CourseCreateResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    request: Request,
    payload: CourseCreateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> CourseCreateResponse:
    course = get_course_service(request).create_course(payload, current_user.uid)
    return CourseCreateResponse(course_id=course.id)


@router.get("", response_model=CourseListResponse)
def list_courses(
    request: Request,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> CourseListResponse:
    return get_course_service(request).list_courses(current_user.uid)


@router.get("/{course_id}", response_model=CourseDetailResponse)
def get_course(
    request: Request,
    course_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> CourseDetailResponse:
    return get_course_service(request).get_course(course_id, current_user.uid)


@router.put("/{course_id}", response_model=CourseDetailResponse)
def update_course(
    request: Request,
    course_id: str,
    payload: CourseUpdateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> CourseDetailResponse:
    return get_course_service(request).update_course(course_id, payload, current_user.uid)


@router.get("/{course_id}/metrics", response_model=CourseMetricsResponse)
def get_course_metrics(
    request: Request,
    course_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> CourseMetricsResponse:
    return get_course_service(request).get_course_metrics(course_id, current_user.uid)


@router.get("/{course_id}/revisions", response_model=CourseRevisionListResponse)
def list_course_revisions(
    request: Request,
    course_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> CourseRevisionListResponse:
    return get_course_service(request).list_revisions(course_id, current_user.uid)


@router.get("/{course_id}/revisions/diff", response_model=CourseRevisionDiffResponse)
def diff_course_revisions(
    request: Request,
    course_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
    from_version: int = Query(alias="from", ge=1),
    to_version: int = Query(alias="to", ge=1),
) -> CourseRevisionDiffResponse:
    return get_course_service(request).diff_revisions(
        course_id,
        from_version,
        to_version,
        current_user.uid,
    )


@router.post(
    "/{course_id}/drill-runs",
    response_model=DrillGenerationStartResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_drill(
    request: Request,
    course_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> DrillGenerationStartResponse:
    drill_run = get_drill_service(request).generate_drill(course_id, current_user.uid)
    return DrillGenerationStartResponse(
        drill_run_id=drill_run.id,
        share_url=f"/drills/{drill_run.share_token}",
    )


@router.get("/{course_id}/drill-runs/{drill_run_id}", response_model=DrillAdminResponse)
def get_course_drill_admin(
    request: Request,
    course_id: str,
    drill_run_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> DrillAdminResponse:
    return get_drill_service(request).get_admin_drill(
        drill_run_id,
        owner_user_id=current_user.uid,
        course_id=course_id,
    )


@router.get("/{course_id}/drill-runs/{drill_run_id}/answers", response_model=DrillAnswersResponse)
def list_course_drill_answers(
    request: Request,
    course_id: str,
    drill_run_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> DrillAnswersResponse:
    return get_drill_service(request).list_answers(
        drill_run_id,
        owner_user_id=current_user.uid,
        course_id=course_id,
    )


@router.post(
    "/{course_id}/drill-runs/{drill_run_id}/analyze",
    response_model=AnalysisStartResponse,
)
def analyze_course_drill(
    request: Request,
    course_id: str,
    drill_run_id: str,
    current_user: Annotated[AuthenticatedUser, Depends(require_current_user)],
) -> AnalysisStartResponse:
    get_drill_service(request).ensure_drill_belongs_to_course(
        drill_run_id,
        course_id,
        current_user.uid,
    )
    patch = get_analysis_service(request).run_analysis(drill_run_id, current_user.uid)
    return AnalysisStartResponse(patch_id=patch.id)
