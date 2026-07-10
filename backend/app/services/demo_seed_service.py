from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256

from app.repositories.repositories import (
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
    ShareTokenRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas import (
    AnswerStatus,
    AnswerSubmission,
    Course,
    DocumentPatch,
    DrillRun,
    PatchStatus,
)
from app.services.demo_seed_data import (
    DemoAnswerDefinition,
    DemoCourseDefinition,
    DemoDrillDefinition,
    demo_course_definitions,
)
from app.utils.diff import build_unified_diff


class DemoSeedService:
    def __init__(
        self,
        *,
        course_repository: CourseRepository,
        drill_repository: DrillRepository,
        share_token_repository: ShareTokenRepository,
        answer_repository: AnswerRepository,
        patch_repository: PatchRepository,
        user_repository: UserRepository,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._course_repository = course_repository
        self._drill_repository = drill_repository
        self._share_token_repository = share_token_repository
        self._answer_repository = answer_repository
        self._patch_repository = patch_repository
        self._user_repository = user_repository
        self._clock = clock or _utc_now

    def ensure_seeded(self, owner_user_id: str) -> None:
        if self._course_repository.list_by_owner(owner_user_id):
            return
        timestamp = self._clock()
        if not self._user_repository.claim_demo_seeded(owner_user_id, timestamp):
            return
        for definition in demo_course_definitions():
            self._seed_course(owner_user_id, definition, timestamp)

    def _seed_course(
        self,
        owner_user_id: str,
        definition: DemoCourseDefinition,
        timestamp: str,
    ) -> None:
        course_id = _seed_id(owner_user_id, definition.slug, "course")
        course = Course(
            id=course_id,
            owner_user_id=owner_user_id,
            title=definition.title,
            markdown=definition.markdown_versions[0],
            drill_focus=definition.drill_focus,
            version=1,
            updated_at=timestamp,
            score_trend=list(definition.score_trend),
            is_demo=True,
        )
        self._course_repository.create(course)

        for version, markdown in enumerate(definition.markdown_versions[1:], start=2):
            course = course.model_copy(
                update={
                    "markdown": markdown,
                    "version": version,
                    "updated_at": timestamp,
                }
            )
            self._course_repository.update(course)

        for drill in definition.drills:
            self._seed_drill(
                owner_user_id,
                definition.slug,
                course.id,
                drill,
                course_title=definition.title,
                course_markdown=definition.markdown_versions[drill.course_version - 1],
            )

        if definition.patch is not None:
            patch_id = _seed_id(owner_user_id, definition.slug, definition.patch.id_suffix)
            drill_run_id = _seed_id(
                owner_user_id,
                definition.slug,
                definition.patch.drill_id_suffix,
            )
            self._patch_repository.create(
                DocumentPatch(
                    id=patch_id,
                    course_id=course.id,
                    drill_run_id=drill_run_id,
                    status=PatchStatus.APPLIED,
                    base_markdown=definition.patch.base_markdown,
                    patched_markdown=definition.patch.patched_markdown,
                    patch_summary=definition.patch.patch_summary,
                    risk_notes=list(definition.patch.risk_notes),
                    diff_text=build_unified_diff(
                        definition.patch.base_markdown,
                        definition.patch.patched_markdown,
                        from_file="v2",
                        to_file="v3",
                    ),
                    failure_signals=list(definition.patch.failure_signals),
                    analysis_timeline=list(definition.patch.analysis_timeline),
                )
            )

        latest_drill = definition.drills[-1]
        self._course_repository.update_summary(
            course.id,
            latest_drill_run_id=_seed_id(owner_user_id, definition.slug, latest_drill.id_suffix),
            latest_drill_status=latest_drill.status,
            answer_count=len(latest_drill.answers),
            latest_patch_id=(
                _seed_id(owner_user_id, definition.slug, definition.patch.id_suffix)
                if definition.patch is not None
                else None
            ),
            latest_patch_status=PatchStatus.APPLIED if definition.patch is not None else None,
            score_trend=list(definition.score_trend),
        )

    def _seed_drill(
        self,
        owner_user_id: str,
        course_slug: str,
        course_id: str,
        definition: DemoDrillDefinition,
        *,
        course_title: str,
        course_markdown: str,
    ) -> None:
        drill_run_id = _seed_id(owner_user_id, course_slug, definition.id_suffix)
        share_token = _seed_id(owner_user_id, course_slug, definition.share_token_suffix)
        self._share_token_repository.reserve(share_token, drill_run_id)
        self._drill_repository.create(
            DrillRun(
                id=drill_run_id,
                course_id=course_id,
                course_version=definition.course_version,
                course_title=course_title,
                course_markdown=course_markdown,
                drill_focus=None,
                status=definition.status,
                questions=list(definition.questions),
                analysis_timeline=list(definition.analysis_timeline),
                share_token=share_token,
            )
        )
        for answer in definition.answers:
            self._seed_answer(
                owner_user_id, course_slug, course_id, drill_run_id, definition, answer
            )

    def _seed_answer(
        self,
        owner_user_id: str,
        course_slug: str,
        course_id: str,
        drill_run_id: str,
        drill: DemoDrillDefinition,
        definition: DemoAnswerDefinition,
    ) -> None:
        max_score = sum(question.max_score for question in drill.questions)
        self._answer_repository.create_submission(
            AnswerSubmission(
                id=_seed_id(owner_user_id, course_slug, definition.id_suffix),
                course_id=course_id,
                drill_run_id=drill_run_id,
                learner_name=definition.learner_name,
                status=AnswerStatus.GRADED,
                answers={question.id: definition.answer_text for question in drill.questions},
                grading_results=list(definition.grading_results),
                total_score=definition.total_score,
                max_score=max_score,
            )
        )


def _seed_id(owner_user_id: str, slug: str, suffix: str) -> str:
    owner_key = sha256(owner_user_id.encode("utf-8")).hexdigest()[:12]
    return f"demo-{owner_key}-{slug}-{suffix}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
