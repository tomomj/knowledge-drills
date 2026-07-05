from typing import cast

from fastapi import APIRouter, Request, status

from app.schemas import LearnerDrillResponse, SubmitAnswerRequest, SubmitAnswerResponse
from app.services.answer_service import AnswerService
from app.services.drill_service import DrillService

router = APIRouter(tags=["drills"])


def get_drill_service(request: Request) -> DrillService:
    return cast(DrillService, request.app.state.drill_service)


def get_answer_service(request: Request) -> AnswerService:
    return cast(AnswerService, request.app.state.answer_service)


@router.get("/api/drills/{share_token}", response_model=LearnerDrillResponse)
async def get_learner_drill(request: Request, share_token: str) -> LearnerDrillResponse:
    return get_drill_service(request).get_learner_drill(share_token)


@router.get(
    "/api/learn/{share_token}",
    response_model=LearnerDrillResponse,
    include_in_schema=False,
)
async def get_learner_drill_legacy(
    request: Request,
    share_token: str,
) -> LearnerDrillResponse:
    return await get_learner_drill(request, share_token)


@router.post(
    "/api/drills/{share_token}/answers",
    response_model=SubmitAnswerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_answer(
    request: Request,
    share_token: str,
    payload: SubmitAnswerRequest,
) -> SubmitAnswerResponse:
    answer = get_answer_service(request).submit_answer(share_token, payload)
    return SubmitAnswerResponse(
        answer_id=answer.id,
        status=answer.status,
        feedback=[result.learner_feedback for result in answer.grading_results],
    )


@router.post(
    "/api/learn/{share_token}/answers",
    response_model=SubmitAnswerResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def submit_answer_legacy(
    request: Request,
    share_token: str,
    payload: SubmitAnswerRequest,
) -> SubmitAnswerResponse:
    return await submit_answer(request, share_token, payload)
