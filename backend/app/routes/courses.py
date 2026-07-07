from typing import cast

from fastapi import APIRouter, Depends, Query, Request, status

from app.auth import require_current_user
from app.errors import AppError
from app.schemas import (
    AnalysisStartResponse,
    CourseCreateRequest,
    CourseCreateResponse,
    CourseDetailResponse,
    CourseListResponse,
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
async def create_course(request: Request, payload: CourseCreateRequest) -> CourseCreateResponse:
    course = get_course_service(request).create_course(payload)
    return CourseCreateResponse(course_id=course.id)


@router.get("", response_model=CourseListResponse)
async def list_courses(request: Request) -> CourseListResponse:
    return get_course_service(request).list_courses()


@router.get("/{course_id}", response_model=CourseDetailResponse)
async def get_course(request: Request, course_id: str) -> CourseDetailResponse:
    return get_course_service(request).get_course(course_id)


@router.put("/{course_id}", response_model=CourseDetailResponse)
async def update_course(
    request: Request,
    course_id: str,
    payload: CourseUpdateRequest,
) -> CourseDetailResponse:
    return get_course_service(request).update_course(course_id, payload)


@router.get("/{course_id}/revisions", response_model=CourseRevisionListResponse)
async def list_course_revisions(
    request: Request,
    course_id: str,
) -> CourseRevisionListResponse:
    return get_course_service(request).list_revisions(course_id)


@router.get("/{course_id}/revisions/diff", response_model=CourseRevisionDiffResponse)
async def diff_course_revisions(
    request: Request,
    course_id: str,
    from_version: int = Query(alias="from", ge=1),
    to_version: int = Query(alias="to", ge=1),
) -> CourseRevisionDiffResponse:
    return get_course_service(request).diff_revisions(course_id, from_version, to_version)


@router.post(
    "/{course_id}/drill-runs",
    response_model=DrillGenerationStartResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_drill(request: Request, course_id: str) -> DrillGenerationStartResponse:
    drill_run = get_drill_service(request).generate_drill(course_id)
    return DrillGenerationStartResponse(
        drill_run_id=drill_run.id,
        share_url=f"/drills/{drill_run.share_token}",
    )


@router.get("/{course_id}/drill-runs/{drill_run_id}", response_model=DrillAdminResponse)
async def get_course_drill_admin(
    request: Request,
    course_id: str,
    drill_run_id: str,
) -> DrillAdminResponse:
    drill = get_drill_service(request).get_admin_drill(drill_run_id)
    if drill.course_id != course_id:
        raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
    return drill


@router.get("/{course_id}/drill-runs/{drill_run_id}/answers", response_model=DrillAnswersResponse)
async def list_course_drill_answers(
    request: Request,
    course_id: str,
    drill_run_id: str,
) -> DrillAnswersResponse:
    drill = get_drill_service(request).get_admin_drill(drill_run_id)
    if drill.course_id != course_id:
        raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
    return get_drill_service(request).list_answers(drill_run_id)


@router.post(
    "/{course_id}/drill-runs/{drill_run_id}/analyze",
    response_model=AnalysisStartResponse,
)
def analyze_course_drill(
    request: Request,
    course_id: str,
    drill_run_id: str,
) -> AnalysisStartResponse:
    drill = get_drill_service(request).get_admin_drill(drill_run_id)
    if drill.course_id != course_id:
        raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
    patch = get_analysis_service(request).run_analysis(drill_run_id)
    return AnalysisStartResponse(patch_id=patch.id)
