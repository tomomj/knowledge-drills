from datetime import UTC, datetime
from uuid import uuid4

from app.errors import AppError
from app.repositories.repositories import (
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
    ShareTokenRepository,
)
from app.schemas import (
    AnswerStatus,
    AnswerSubmission,
    Course,
    CourseCreateRequest,
    CourseDetailResponse,
    CourseListResponse,
    CourseMetricsResponse,
    CourseMetricsRun,
    CourseRevisionDiffResponse,
    CourseRevisionListResponse,
    CourseRevisionSummary,
    CourseScoreTrendPoint,
    CourseSummary,
    CourseUpdateRequest,
    DrillRun,
)
from app.utils.diff import build_unified_diff

MAX_COURSE_MARKDOWN_CHARS = 20_000


class CourseService:
    def __init__(
        self,
        course_repository: CourseRepository,
        drill_repository: DrillRepository | None = None,
        answer_repository: AnswerRepository | None = None,
        patch_repository: PatchRepository | None = None,
        share_token_repository: ShareTokenRepository | None = None,
    ) -> None:
        self._course_repository = course_repository
        self._drill_repository = drill_repository
        self._answer_repository = answer_repository
        self._patch_repository = patch_repository
        self._share_token_repository = share_token_repository

    def create_course(
        self,
        request: CourseCreateRequest,
        owner_user_id: str,
    ) -> CourseDetailResponse:
        self._validate_title_and_markdown(request.title, request.markdown)
        course = Course(
            id=uuid4().hex,
            owner_user_id=owner_user_id,
            title=request.title,
            markdown=request.markdown,
            drill_focus=self._normalize_drill_focus(request.drill_focus),
            version=1,
            updated_at=_utc_now(),
        )
        self._course_repository.create(course)
        return CourseDetailResponse.model_validate(course.model_dump())

    def get_course(self, course_id: str, owner_user_id: str) -> CourseDetailResponse:
        course = self._get_owned_course_or_404(course_id, owner_user_id)
        return CourseDetailResponse.model_validate(course.model_dump())

    def update_course(
        self,
        course_id: str,
        request: CourseUpdateRequest,
        owner_user_id: str,
    ) -> CourseDetailResponse:
        self._validate_title_and_markdown(request.title, request.markdown)
        course = self._get_owned_course_or_404(course_id, owner_user_id)

        updated = course.model_copy(
            update={
                "title": request.title,
                "markdown": request.markdown,
                "drill_focus": self._normalize_drill_focus(request.drill_focus),
                "version": course.version + 1,
                "updated_at": _utc_now(),
            }
        )
        self._course_repository.update(updated)
        return CourseDetailResponse.model_validate(updated.model_dump())

    def list_courses(self, owner_user_id: str) -> CourseListResponse:
        summaries = [
            self._summarize(course)
            for course in self._course_repository.list_by_owner(owner_user_id)
        ]
        # updatedAt 降順、updatedAt なしは末尾
        summaries.sort(key=lambda summary: summary.updated_at or "", reverse=True)
        return CourseListResponse(courses=summaries)

    def delete_course(self, course_id: str, owner_user_id: str) -> None:
        self._get_owned_course_or_404(course_id, owner_user_id)
        if (
            self._drill_repository is None
            or self._answer_repository is None
            or self._patch_repository is None
            or self._share_token_repository is None
        ):
            raise RuntimeError("CourseService delete dependencies are not configured")

        drill_runs = self._drill_repository.list_by_course(course_id)
        for drill_run in drill_runs:
            if drill_run.share_token:
                self._share_token_repository.delete(drill_run.share_token)
            for answer in self._answer_repository.list_by_drill_run(drill_run.id):
                self._answer_repository.delete(answer.id)
            self._drill_repository.delete(drill_run.id)

        for patch in self._patch_repository.list_by_course(course_id):
            self._patch_repository.delete(patch.id)

        for revision in self._course_repository.list_revisions(course_id):
            self._course_repository.delete_revision(course_id, revision.version)

        self._course_repository.delete(course_id)

    def list_revisions(
        self,
        course_id: str,
        owner_user_id: str,
    ) -> CourseRevisionListResponse:
        self._get_owned_course_or_404(course_id, owner_user_id)
        revisions = self._course_repository.list_revisions(course_id)
        revisions.sort(key=lambda revision: revision.version, reverse=True)
        return CourseRevisionListResponse(
            revisions=[
                CourseRevisionSummary(
                    version=revision.version,
                    title=revision.title,
                    updated_at=revision.updated_at,
                )
                for revision in revisions
            ]
        )

    def get_course_metrics(self, course_id: str, owner_user_id: str) -> CourseMetricsResponse:
        self._get_owned_course_or_404(course_id, owner_user_id)
        if self._drill_repository is None or self._answer_repository is None:
            raise RuntimeError("CourseService metrics dependencies are not configured")

        drill_runs = self._drill_repository.list_by_course(course_id)
        drill_runs.sort(key=lambda drill_run: (drill_run.course_version, drill_run.id))
        return CourseMetricsResponse(
            course_id=course_id,
            runs=[self._build_metrics_run(drill_run) for drill_run in drill_runs],
        )

    def diff_revisions(
        self,
        course_id: str,
        from_version: int,
        to_version: int,
        owner_user_id: str,
    ) -> CourseRevisionDiffResponse:
        self._get_owned_course_or_404(course_id, owner_user_id)
        from_revision = self._course_repository.get_revision(course_id, from_version)
        to_revision = self._course_repository.get_revision(course_id, to_version)
        if from_revision is None or to_revision is None:
            raise AppError(
                "course_revision_not_found",
                "Course revision was not found.",
                status_code=404,
            )
        diff_text = build_unified_diff(
            from_revision.markdown,
            to_revision.markdown,
            from_file=f"v{from_version}",
            to_file=f"v{to_version}",
        )
        return CourseRevisionDiffResponse(
            from_version=from_version,
            to_version=to_version,
            diff_text=diff_text,
        )

    def _get_owned_course_or_404(self, course_id: str, owner_user_id: str) -> Course:
        course = self._course_repository.get(course_id)
        if course is None or course.owner_user_id != owner_user_id:
            raise AppError("course_not_found", "Course was not found.", status_code=404)
        return course

    def _summarize(self, course: Course) -> CourseSummary:
        drill_status = course.latest_drill_status
        answer_count = course.answer_count
        patch_status = course.latest_patch_status
        score_trend = course.score_trend

        if (
            course.latest_drill_run_id
            and drill_status is None
            and self._drill_repository is not None
        ):
            drill_run = self._drill_repository.get(course.latest_drill_run_id)
            if drill_run is not None:
                drill_status = drill_run.status
                if self._answer_repository is not None:
                    answer_count = len(self._answer_repository.list_by_drill_run(drill_run.id))

        if course.latest_patch_id and patch_status is None and self._patch_repository is not None:
            patch = self._patch_repository.get(course.latest_patch_id)
            if patch is not None:
                patch_status = patch.status

        score_trend_changed = False
        if (
            score_trend is None
            and answer_count > 0
            and self._drill_repository is not None
            and self._answer_repository is not None
        ):
            score_trend = self._build_score_trend(course.id)
            score_trend_changed = True

        if (
            drill_status != course.latest_drill_status
            or answer_count != course.answer_count
            or patch_status != course.latest_patch_status
            or score_trend_changed
        ):
            self._course_repository.update_summary(
                course.id,
                latest_drill_run_id=course.latest_drill_run_id,
                latest_drill_status=drill_status,
                answer_count=answer_count,
                latest_patch_id=course.latest_patch_id,
                latest_patch_status=patch_status,
                score_trend=score_trend if score_trend_changed else None,
            )

        return CourseSummary(
            id=course.id,
            title=course.title,
            version=course.version,
            updated_at=course.updated_at,
            drill_status=drill_status,
            answer_count=answer_count,
            patch_status=patch_status,
            latest_drill_run_id=course.latest_drill_run_id,
            latest_patch_id=course.latest_patch_id,
            score_trend=score_trend,
            is_demo=course.is_demo,
        )

    def _build_metrics_run(self, drill_run: DrillRun) -> CourseMetricsRun:
        if self._answer_repository is None:
            raise RuntimeError("CourseService metrics dependencies are not configured")
        answers = self._answer_repository.list_by_drill_run(drill_run.id)
        graded_answers = [answer for answer in answers if answer.status == AnswerStatus.GRADED]
        total_scores = [
            answer.total_score for answer in graded_answers if answer.total_score is not None
        ]
        return CourseMetricsRun(
            drill_run_id=drill_run.id,
            course_version=drill_run.course_version,
            answer_count=len(answers),
            average_score=_average(total_scores),
            max_score=_drill_max_score(drill_run, graded_answers),
        )

    def _build_score_trend(self, course_id: str) -> list[CourseScoreTrendPoint]:
        if self._drill_repository is None:
            raise RuntimeError("CourseService metrics dependencies are not configured")
        drill_runs = self._drill_repository.list_by_course(course_id)
        drill_runs.sort(key=lambda drill_run: (drill_run.course_version, drill_run.id))
        by_version: dict[int, CourseScoreTrendPoint] = {}
        for drill_run in drill_runs:
            metrics_run = self._build_metrics_run(drill_run)
            if metrics_run.average_score is None or metrics_run.max_score is None:
                continue
            by_version[metrics_run.course_version] = CourseScoreTrendPoint(
                course_version=metrics_run.course_version,
                average_score=metrics_run.average_score,
                max_score=metrics_run.max_score,
            )
        return [by_version[version] for version in sorted(by_version)]

    def _validate_title_and_markdown(self, title: str, markdown: str) -> None:
        if not title.strip():
            raise AppError("course_title_required", "Course title is required.")
        if not markdown.strip():
            raise AppError("course_markdown_required", "Course markdown is required.")
        if len(markdown) > MAX_COURSE_MARKDOWN_CHARS:
            raise AppError(
                "course_markdown_too_long",
                "Course markdown exceeds the MVP character limit.",
            )

    def _normalize_drill_focus(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _average(values: list[int]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _drill_max_score(drill_run: DrillRun, graded_answers: list[AnswerSubmission]) -> int | None:
    question_total = sum(question.max_score for question in drill_run.questions)
    if question_total > 0:
        return question_total
    for answer in graded_answers:
        if answer.max_score is not None:
            return answer.max_score
    return None
