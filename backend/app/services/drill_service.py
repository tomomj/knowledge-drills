import logging
from collections.abc import Iterable
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
    AnswerStatus,
    AnswerSubmission,
    DrillAdminResponse,
    DrillAnswerAdminItem,
    DrillAnswersResponse,
    DrillGenerationRequest,
    DrillQuestion,
    DrillRun,
    DrillRunStatus,
    DrillScoreSummary,
    GradingResult,
    LearnerDrillQuestionResponse,
    LearnerDrillResponse,
    QuestionScoreSummary,
    SourceEvidence,
)
from app.services.drill_status_policy import is_distributable_drill_status
from app.services.share_token_service import ShareTokenService

logger = logging.getLogger("app.drill")


class DrillGenerationValidationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        question_id: str | None = None,
        evidence_index: int | None = None,
        section_heading: str | None = None,
        excerpt: str | None = None,
    ) -> None:
        super().__init__(message)
        self.question_id = question_id
        self.evidence_index = evidence_index
        self.section_heading_preview = _preview_text(section_heading)
        self.excerpt_preview = _preview_text(excerpt)
        self.excerpt_length = len(excerpt) if excerpt is not None else None


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

    def generate_drill(self, course_id: str, owner_user_id: str) -> DrillRun:
        course = self._course_repository.get(course_id)
        if course is None or course.owner_user_id != owner_user_id:
            raise AppError("course_not_found", "Course was not found.", status_code=404)

        drill_run = DrillRun(
            id=uuid4().hex,
            course_id=course.id,
            course_version=course.version,
            course_title=course.title,
            course_markdown=course.markdown,
            drill_focus=course.drill_focus,
            status=DrillRunStatus.GENERATING,
        )
        self._share_token_service.create_drill_run_with_reserved_token(drill_run)
        saved_drill_run = self._drill_repository.get(drill_run.id)
        if saved_drill_run is None:
            raise RuntimeError("drill run was not created")
        self._course_repository.update_summary(
            course.id,
            latest_drill_run_id=saved_drill_run.id,
            latest_drill_status=saved_drill_run.status,
            answer_count=0,
        )

        try:
            agent_response = self._agent_client.generate_drill(
                DrillGenerationRequest(
                    course_title=course.title,
                    course_markdown=course.markdown,
                    drill_focus=course.drill_focus,
                )
            )
            questions = self._validate_and_normalize_questions(
                agent_response.questions,
                course.markdown,
            )
        except DrillGenerationValidationError as exc:
            logger.warning(
                "drill generation validation failed course_id=%s drill_run_id=%s reason=%s "
                "question_id=%s evidence_index=%s section_heading=%s excerpt_preview=%s "
                "excerpt_length=%s",
                course.id,
                saved_drill_run.id,
                str(exc),
                exc.question_id,
                exc.evidence_index,
                exc.section_heading_preview,
                exc.excerpt_preview,
                exc.excerpt_length,
            )
            return self._mark_generation_failed(saved_drill_run, course.id)
        except Exception:
            self._mark_generation_failed(saved_drill_run, course.id)
            raise

        ready = saved_drill_run.model_copy(
            update={
                "status": DrillRunStatus.READY,
                "questions": questions,
                "error_message": None,
            }
        )
        self._drill_repository.update(ready)
        self._course_repository.update_summary(
            course.id,
            latest_drill_run_id=ready.id,
            latest_drill_status=ready.status,
            answer_count=0,
        )
        return ready

    def get_admin_drill(
        self,
        drill_run_id: str,
        *,
        owner_user_id: str,
        course_id: str | None = None,
    ) -> DrillAdminResponse:
        drill_run = self._get_owned_drill_or_404(
            drill_run_id,
            owner_user_id=owner_user_id,
            course_id=course_id,
        )

        submissions = (
            self._answer_repository.list_by_drill_run(drill_run.id)
            if self._answer_repository is not None
            else []
        )
        answer_count = self._stored_answer_count(drill_run)
        if answer_count is None:
            answer_count = len(submissions)
        score_summary = self._build_score_summary(drill_run, submissions)

        return DrillAdminResponse(
            id=drill_run.id,
            course_id=drill_run.course_id,
            course_version=drill_run.course_version,
            drill_focus=drill_run.drill_focus,
            status=drill_run.status,
            questions=[
                AdminDrillQuestionResponse.from_domain(question) for question in drill_run.questions
            ],
            rubric_summary=self._build_rubric_summary(drill_run.questions),
            share_url=f"/drills/{drill_run.share_token}" if drill_run.share_token else None,
            answer_count=answer_count,
            score_summary=score_summary,
            analysis_timeline=drill_run.analysis_timeline,
            can_analyze=score_summary.graded_answer_count > 0,
            error_message=drill_run.error_message,
        )

    def list_answers(
        self,
        drill_run_id: str,
        *,
        owner_user_id: str,
        course_id: str | None = None,
    ) -> DrillAnswersResponse:
        drill_run = self._get_owned_drill_or_404(
            drill_run_id,
            owner_user_id=owner_user_id,
            course_id=course_id,
        )
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

    def ensure_drill_belongs_to_course(
        self,
        drill_run_id: str,
        course_id: str,
        owner_user_id: str,
    ) -> DrillRun:
        return self._get_owned_drill_or_404(
            drill_run_id,
            owner_user_id=owner_user_id,
            course_id=course_id,
        )

    def _get_owned_drill_or_404(
        self,
        drill_run_id: str,
        *,
        owner_user_id: str,
        course_id: str | None = None,
    ) -> DrillRun:
        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
        if course_id is not None and drill_run.course_id != course_id:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
        course = self._course_repository.get(drill_run.course_id)
        if course is None or course.owner_user_id != owner_user_id:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
        return drill_run

    def get_learner_drill(self, share_token: str) -> LearnerDrillResponse:
        if self._share_token_repository is None:
            raise AppError("invalid_share_token", "Share token is invalid.", status_code=404)
        drill_run_id = self._share_token_repository.get_drill_run_id(share_token)
        if drill_run_id is None:
            raise AppError("invalid_share_token", "Share token is invalid.", status_code=404)

        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None or not is_distributable_drill_status(drill_run.status):
            raise AppError("invalid_share_token", "Share token is invalid.", status_code=404)

        course_title, course_markdown = self._resolve_learner_course_snapshot(drill_run)
        return LearnerDrillResponse(
            drill_run_id=drill_run.id,
            course_id=drill_run.course_id,
            course_title=course_title,
            course_markdown=course_markdown,
            course_version=drill_run.course_version,
            questions=[
                LearnerDrillQuestionResponse.from_domain(question)
                for question in drill_run.questions
            ],
        )

    def _resolve_learner_course_snapshot(self, drill_run: DrillRun) -> tuple[str, str]:
        course_title = drill_run.course_title
        course_markdown = drill_run.course_markdown
        if course_title is None or course_markdown is None:
            # スナップショットを持たない既存 drill run は現行 course の値にフォールバックする
            course = self._course_repository.get(drill_run.course_id)
            if course is not None:
                course_title = course_title if course_title is not None else course.title
                course_markdown = (
                    course_markdown if course_markdown is not None else course.markdown
                )
        return course_title or "", course_markdown or ""

    def _validate_and_normalize_questions(
        self,
        questions: list[DrillQuestion],
        course_markdown: str,
    ) -> list[DrillQuestion]:
        if len(questions) != 3:
            raise DrillGenerationValidationError(
                "drill generation must return exactly three questions"
            )
        normalized_questions: list[DrillQuestion] = []
        for question in questions:
            rubric_total = sum(item.points for item in question.rubric)
            if rubric_total != question.max_score:
                raise DrillGenerationValidationError(
                    "rubric points must total max_score",
                    question_id=question.id,
                )
            if not question.source_evidence:
                raise DrillGenerationValidationError(
                    "source evidence is required",
                    question_id=question.id,
                )
            normalized_evidence: list[SourceEvidence] = []
            for evidence_index, evidence in enumerate(question.source_evidence):
                normalized_evidence.append(
                    self._normalize_source_evidence(
                        evidence,
                        course_markdown,
                        question_id=question.id,
                        evidence_index=evidence_index,
                    )
                )
            normalized_questions.append(
                question.model_copy(update={"source_evidence": normalized_evidence})
            )
        return normalized_questions

    def _normalize_source_evidence(
        self,
        evidence: SourceEvidence,
        course_markdown: str,
        *,
        question_id: str,
        evidence_index: int,
    ) -> SourceEvidence:
        excerpt = evidence.excerpt.strip()
        if not excerpt:
            raise DrillGenerationValidationError(
                "source evidence excerpt is required",
                question_id=question_id,
                evidence_index=evidence_index,
                section_heading=evidence.section_heading,
                excerpt=evidence.excerpt,
            )

        normalized_excerpt = _find_course_excerpt(evidence, course_markdown)
        if normalized_excerpt is not None:
            return evidence.model_copy(update={"excerpt": normalized_excerpt})
        if excerpt in course_markdown:
            return evidence.model_copy(update={"excerpt": excerpt})
        raise DrillGenerationValidationError(
            "source evidence excerpt must match course markdown",
            question_id=question_id,
            evidence_index=evidence_index,
            section_heading=evidence.section_heading,
            excerpt=evidence.excerpt,
        )

    def _mark_generation_failed(self, drill_run: DrillRun, course_id: str) -> DrillRun:
        failed = drill_run.model_copy(
            update={
                "status": DrillRunStatus.FAILED,
                "error_message": "drill generation failed",
            }
        )
        self._drill_repository.update(failed)
        self._course_repository.update_summary(
            course_id,
            latest_drill_run_id=failed.id,
            latest_drill_status=failed.status,
            answer_count=0,
        )
        return failed

    def _build_rubric_summary(self, questions: list[DrillQuestion]) -> list[str]:
        return [
            f"{question.id}: {', '.join(item.criterion for item in question.rubric)}"
            for question in questions
        ]

    def _build_score_summary(
        self,
        drill_run: DrillRun,
        answers: list[AnswerSubmission],
    ) -> DrillScoreSummary:
        graded_answers = [answer for answer in answers if answer.status == AnswerStatus.GRADED]
        total_scores = [
            answer.total_score for answer in graded_answers if answer.total_score is not None
        ]
        max_score = sum(question.max_score for question in drill_run.questions)

        return DrillScoreSummary(
            graded_answer_count=len(graded_answers),
            average_score=_average(total_scores),
            max_score=max_score,
            questions=[
                self._build_question_score_summary(question, graded_answers)
                for question in drill_run.questions
            ],
        )

    def _build_question_score_summary(
        self,
        question: DrillQuestion,
        graded_answers: list[AnswerSubmission],
    ) -> QuestionScoreSummary:
        results = [
            result
            for answer in graded_answers
            for result in answer.grading_results
            if result.question_id == question.id
        ]
        return QuestionScoreSummary(
            question_id=question.id,
            average_score=_average(result.score for result in results),
            max_score=question.max_score,
            graded_answer_count=len(results),
            common_missing_points=_top_frequent_strings(
                (
                    missing_point
                    for result in results
                    for missing_point in result.missing_points
                ),
                min_count=2,
                limit=3,
            ),
            failure_tags=_top_failure_tags(results),
        )

    def _stored_answer_count(self, drill_run: DrillRun) -> int | None:
        course = self._course_repository.get(drill_run.course_id)
        if course is None or course.latest_drill_run_id != drill_run.id:
            return None
        return course.answer_count


def _average(values: Iterable[int]) -> float | None:
    materialized = list(values)
    if not materialized:
        return None
    return sum(materialized) / len(materialized)


def _preview_text(value: str | None, *, limit: int = 120) -> str | None:
    if value is None:
        return None
    preview = _compact_whitespace(value)
    if len(preview) <= limit:
        return preview
    return f"{preview[: limit - 3]}..."


def _find_course_excerpt(evidence: SourceEvidence, course_markdown: str) -> str | None:
    excerpt_heading = _find_course_heading(evidence.excerpt, course_markdown)
    if excerpt_heading is not None:
        return excerpt_heading

    compact_excerpt = _compact_whitespace(evidence.excerpt)
    if not compact_excerpt:
        return None
    for candidate in _course_excerpt_candidates(course_markdown):
        if _compact_whitespace(candidate) == compact_excerpt:
            return candidate
    whitespace_insensitive_excerpt = _find_whitespace_insensitive_course_excerpt(
        evidence.excerpt,
        course_markdown,
    )
    if whitespace_insensitive_excerpt is not None:
        return whitespace_insensitive_excerpt
    return _find_course_heading(evidence.section_heading, course_markdown)


def _find_course_heading(heading: str, course_markdown: str) -> str | None:
    heading_text = _heading_text(heading)
    if not heading_text:
        return None
    for line in course_markdown.splitlines():
        candidate = line.strip()
        if (
            candidate
            and _is_markdown_heading(candidate)
            and _heading_text(candidate) == heading_text
        ):
            return candidate if candidate in course_markdown else line
    return None


def _find_whitespace_insensitive_course_excerpt(
    excerpt: str,
    course_markdown: str,
) -> str | None:
    normalized_excerpt = _remove_whitespace(excerpt)
    if not normalized_excerpt:
        return None

    normalized_course, original_indexes = _remove_whitespace_with_indexes(course_markdown)
    start_index = normalized_course.find(normalized_excerpt)
    if start_index == -1:
        return None

    end_index = start_index + len(normalized_excerpt) - 1
    original_start = original_indexes[start_index]
    original_end = original_indexes[end_index] + 1
    return course_markdown[original_start:original_end].strip()


def _remove_whitespace(value: str) -> str:
    return "".join(char for char in value if not char.isspace())


def _remove_whitespace_with_indexes(value: str) -> tuple[str, list[int]]:
    normalized_chars: list[str] = []
    original_indexes: list[int] = []
    for index, char in enumerate(value):
        if char.isspace():
            continue
        normalized_chars.append(char)
        original_indexes.append(index)
    return "".join(normalized_chars), original_indexes


def _heading_text(value: str) -> str:
    return value.strip().lstrip("#").strip()


def _is_markdown_heading(value: str) -> bool:
    return value.strip().startswith("#")


def _compact_whitespace(value: str) -> str:
    return " ".join(value.split())


def _course_excerpt_candidates(course_markdown: str) -> Iterable[str]:
    for line in course_markdown.splitlines():
        candidate = line.strip()
        if candidate:
            yield candidate if candidate in course_markdown else line

    paragraph: list[str] = []
    for line in course_markdown.splitlines():
        if line.strip():
            paragraph.append(line)
            continue
        yield from _flush_paragraph_candidate(paragraph, course_markdown)
        paragraph = []
    yield from _flush_paragraph_candidate(paragraph, course_markdown)


def _flush_paragraph_candidate(
    paragraph: list[str],
    course_markdown: str,
) -> Iterable[str]:
    if not paragraph:
        return
    candidate = "\n".join(paragraph).strip()
    if candidate:
        yield candidate if candidate in course_markdown else "\n".join(paragraph)


def _top_failure_tags(results: list[GradingResult]) -> list[str]:
    deduplicated_tags: list[str] = []
    for result in results:
        seen_in_result: set[str] = set()
        for tag in result.failure_tags:
            if tag not in seen_in_result:
                deduplicated_tags.append(tag)
                seen_in_result.add(tag)
    return _top_frequent_strings(deduplicated_tags, min_count=1, limit=3)


def _top_frequent_strings(
    values: Iterable[str],
    *,
    min_count: int,
    limit: int,
) -> list[str]:
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, value in enumerate(values):
        if value not in first_seen:
            first_seen[value] = index
        counts[value] = counts.get(value, 0) + 1

    ranked = [
        value
        for value, count in counts.items()
        if count >= min_count
    ]
    ranked.sort(key=lambda value: (-counts[value], first_seen[value]))
    return ranked[:limit]
