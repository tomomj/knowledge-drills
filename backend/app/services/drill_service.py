from uuid import uuid4

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.errors import AppError
from app.repositories.repositories import (
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    ShareTokenRepository,
)
from app.schemas import (
    AdminDrillQuestionResponse,
    DrillAdminResponse,
    DrillAnswerAdminItem,
    DrillAnswersResponse,
    DrillGenerationRequest,
    DrillQuestion,
    DrillRun,
    DrillRunStatus,
    LearnerDrillQuestionResponse,
    LearnerDrillResponse,
)
from app.services.share_token_service import ShareTokenService


class DrillService:
    def __init__(
        self,
        *,
        course_repository: CourseRepository,
        drill_repository: DrillRepository,
        share_token_service: ShareTokenService,
        agent_client: AgentRuntimeClient,
        answer_repository: AnswerRepository | None = None,
        share_token_repository: ShareTokenRepository | None = None,
    ) -> None:
        self._course_repository = course_repository
        self._drill_repository = drill_repository
        self._share_token_service = share_token_service
        self._agent_client = agent_client
        self._answer_repository = answer_repository
        self._share_token_repository = share_token_repository

    def generate_drill(self, course_id: str) -> DrillRun:
        course = self._course_repository.get(course_id)
        if course is None:
            raise AppError("course_not_found", "Course was not found.", status_code=404)

        drill_run = DrillRun(
            id=uuid4().hex,
            course_id=course.id,
            course_version=course.version,
            status=DrillRunStatus.GENERATING,
        )
        self._share_token_service.create_drill_run_with_reserved_token(drill_run)
        saved_drill_run = self._drill_repository.get(drill_run.id)
        if saved_drill_run is None:
            raise RuntimeError("drill run was not created")

        try:
            agent_response = self._agent_client.generate_drill(
                DrillGenerationRequest(
                    course_title=course.title,
                    course_markdown=course.markdown,
                )
            )
            self._validate_questions(agent_response.questions)
        except Exception:
            failed = saved_drill_run.model_copy(
                update={
                    "status": DrillRunStatus.FAILED,
                    "error_message": "drill generation failed",
                }
            )
            self._drill_repository.update(failed)
            raise

        ready = saved_drill_run.model_copy(
            update={
                "status": DrillRunStatus.READY,
                "questions": agent_response.questions,
                "error_message": None,
            }
        )
        self._drill_repository.update(ready)
        self._course_repository.update(
            course.model_copy(update={"latest_drill_run_id": ready.id})
        )
        return ready

    def get_admin_drill(self, drill_run_id: str) -> DrillAdminResponse:
        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)

        answer_count = 0
        if self._answer_repository is not None:
            answer_count = len(self._answer_repository.list_by_drill_run(drill_run.id))

        return DrillAdminResponse(
            id=drill_run.id,
            course_id=drill_run.course_id,
            course_version=drill_run.course_version,
            status=drill_run.status,
            questions=[
                AdminDrillQuestionResponse.from_domain(question) for question in drill_run.questions
            ],
            rubric_summary=self._build_rubric_summary(drill_run.questions),
            share_url=f"/drills/{drill_run.share_token}" if drill_run.share_token else None,
            answer_count=answer_count,
            can_analyze=answer_count > 0,
            error_message=drill_run.error_message,
        )

    def list_answers(self, drill_run_id: str) -> DrillAnswersResponse:
        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
        submissions = (
            self._answer_repository.list_by_drill_run(drill_run.id)
            if self._answer_repository is not None
            else []
        )
        return DrillAnswersResponse(
            course_version=drill_run.course_version,
            answers=[
                DrillAnswerAdminItem(
                    id=submission.id,
                    learner_name=submission.learner_name,
                    status=submission.status,
                    total_score=submission.total_score,
                    max_score=submission.max_score,
                    answers=submission.answers,
                    grading_results=submission.grading_results,
                )
                for submission in submissions
            ],
        )

    def get_learner_drill(self, share_token: str) -> LearnerDrillResponse:
        if self._share_token_repository is None:
            raise AppError("invalid_share_token", "Share token is invalid.", status_code=404)
        drill_run_id = self._share_token_repository.get_drill_run_id(share_token)
        if drill_run_id is None:
            raise AppError("invalid_share_token", "Share token is invalid.", status_code=404)

        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None or drill_run.status != DrillRunStatus.READY:
            raise AppError("invalid_share_token", "Share token is invalid.", status_code=404)

        return LearnerDrillResponse(
            drill_run_id=drill_run.id,
            course_id=drill_run.course_id,
            questions=[
                LearnerDrillQuestionResponse.from_domain(question)
                for question in drill_run.questions
            ],
        )

    def _validate_questions(self, questions: list[DrillQuestion]) -> None:
        if len(questions) != 3:
            raise ValueError("drill generation must return exactly three questions")
        for question in questions:
            rubric_total = sum(item.points for item in question.rubric)
            if rubric_total != question.max_score:
                raise ValueError("rubric points must total max_score")
            if not question.source_evidence:
                raise ValueError("source evidence is required")

    def _build_rubric_summary(self, questions: list[DrillQuestion]) -> list[str]:
        return [
            f"{question.id}: {', '.join(item.criterion for item in question.rubric)}"
            for question in questions
        ]
