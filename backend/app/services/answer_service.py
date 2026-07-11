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
    CourseScoreTrendPoint,
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

        share = self._share_token_repository.get(share_token)
        if share is None:
            raise AppError("invalid_share_token", "Share token is invalid.", status_code=404)
        if share.closed_at is not None:
            raise AppError("share_closed", "Answer collection has ended.", status_code=410)
        drill_run = self._drill_repository.get(share.drill_run_id)
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
        if self._course_repository is not None:
            self._update_course_score_trend(drill_run)
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

    def _update_course_score_trend(self, drill_run: DrillRun) -> None:
        if self._answer_repository is None or self._course_repository is None:
            return
        graded_answers = [
            answer
            for answer in self._answer_repository.list_by_drill_run(drill_run.id)
            if answer.status == AnswerStatus.GRADED
        ]
        total_scores = [
            answer.total_score for answer in graded_answers if answer.total_score is not None
        ]
        average_score = _average(total_scores)
        if average_score is None:
            return
        max_score = sum(question.max_score for question in drill_run.questions)
        if max_score <= 0:
            for answer in graded_answers:
                if answer.max_score is not None:
                    max_score = answer.max_score
                    break
        if max_score <= 0:
            return
        self._course_repository.update_score_trend_point(
            drill_run.course_id,
            CourseScoreTrendPoint(
                course_version=drill_run.course_version,
                average_score=average_score,
                max_score=max_score,
            ),
        )


def _average(values: list[int]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)
