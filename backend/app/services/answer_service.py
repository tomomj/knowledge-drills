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
    AnswerStatus,
    AnswerSubmission,
    DrillRun,
    GradingRequest,
    SubmitAnswerRequest,
)
from app.services.drill_status_policy import is_distributable_drill_status

EXPECTED_ANSWER_COUNT = 3


class AnswerService:
    def __init__(
        self,
        *,
        course_repository: CourseRepository | None = None,
        drill_repository: DrillRepository | None = None,
        answer_repository: AnswerRepository | None = None,
        share_token_repository: ShareTokenRepository | None = None,
        agent_client: AgentRuntimeClient | None = None,
    ) -> None:
        self._course_repository = course_repository
        self._drill_repository = drill_repository
        self._answer_repository = answer_repository
        self._share_token_repository = share_token_repository
        self._agent_client = agent_client

    def submit_answer(self, share_token: str, request: SubmitAnswerRequest) -> AnswerSubmission:
        if (
            self._drill_repository is None
            or self._answer_repository is None
            or self._share_token_repository is None
            or self._agent_client is None
        ):
            raise RuntimeError("AnswerService dependencies are not configured")

        drill_run_id = self._share_token_repository.get_drill_run_id(share_token)
        if drill_run_id is None:
            raise AppError("invalid_share_token", "Share token is invalid.", status_code=404)
        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None or not is_distributable_drill_status(drill_run.status):
            raise AppError("invalid_share_token", "Share token is invalid.", status_code=404)

        answers_by_question_id = self.validate_submission(drill_run, request)
        answer = AnswerSubmission(
            id=uuid4().hex,
            course_id=drill_run.course_id,
            drill_run_id=drill_run.id,
            learner_name=request.learner_name,
            status=AnswerStatus.GRADING,
            answers=answers_by_question_id,
        )
        self._answer_repository.create_submission(answer)
        if self._course_repository is not None:
            self._course_repository.increment_answer_count(drill_run.course_id)

        try:
            grading_results = [
                self._agent_client.grade_answer(
                    GradingRequest(
                        question=question,
                        learner_answer=answers_by_question_id[question.id],
                    )
                )
                for question in drill_run.questions
            ]
        except Exception:
            failed = answer.model_copy(
                update={
                    "status": AnswerStatus.FAILED,
                    "error_message": "grading failed",
                }
            )
            self._answer_repository.update(failed)
            raise

        graded = answer.model_copy(
            update={
                "status": AnswerStatus.GRADED,
                "grading_results": grading_results,
                "total_score": sum(result.score for result in grading_results),
                "max_score": sum(result.max_score for result in grading_results),
            }
        )
        self._answer_repository.update(graded)
        return graded

    def validate_submission(
        self,
        drill_run: DrillRun,
        request: SubmitAnswerRequest,
    ) -> dict[str, str]:
        if not request.learner_name.strip():
            raise AppError("learner_name_required", "Learner name is required.")
        if len(request.answers) != EXPECTED_ANSWER_COUNT:
            raise AppError("answer_count_invalid", "Exactly three answers are required.")

        answers_by_question_id: dict[str, str] = {}
        for answer in request.answers:
            if not answer.answer_text.strip():
                raise AppError("answer_text_required", "Every answer is required.")
            if answer.question_id in answers_by_question_id:
                raise AppError("answer_question_duplicate", "Answer question ids must be unique.")
            answers_by_question_id[answer.question_id] = answer.answer_text

        expected_question_ids = {question.id for question in drill_run.questions}
        actual_question_ids = set(answers_by_question_id)
        if actual_question_ids != expected_question_ids:
            raise AppError(
                "answer_question_mismatch",
                "Answer question ids must match the drill questions.",
            )

        return answers_by_question_id
