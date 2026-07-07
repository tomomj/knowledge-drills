from datetime import UTC, datetime
from uuid import uuid4

from app.errors import AppError
from app.repositories.repositories import (
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
)
from app.schemas import (
    Course,
    CourseCreateRequest,
    CourseDetailResponse,
    CourseListResponse,
    CourseRevisionDiffResponse,
    CourseRevisionListResponse,
    CourseRevisionSummary,
    CourseSummary,
    CourseUpdateRequest,
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
    ) -> None:
        self._course_repository = course_repository
        self._drill_repository = drill_repository
        self._answer_repository = answer_repository
        self._patch_repository = patch_repository

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

        if (
            drill_status != course.latest_drill_status
            or answer_count != course.answer_count
            or patch_status != course.latest_patch_status
        ):
            self._course_repository.update_summary(
                course.id,
                latest_drill_run_id=course.latest_drill_run_id,
                latest_drill_status=drill_status,
                answer_count=answer_count,
                latest_patch_id=course.latest_patch_id,
                latest_patch_status=patch_status,
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
        )

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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
