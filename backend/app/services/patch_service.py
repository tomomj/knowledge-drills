from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

from app.errors import AppError
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import CourseRepository, PatchRepository
from app.schemas import Course, DocumentPatch, PatchStatus

T = TypeVar("T")


class PatchService:
    def __init__(
        self,
        course_repository: CourseRepository,
        patch_repository: PatchRepository,
        firestore_client: InMemoryFirestoreClient,
    ) -> None:
        self._course_repository = course_repository
        self._patch_repository = patch_repository
        self._firestore_client = firestore_client

    def get_patch(self, patch_id: str) -> DocumentPatch:
        patch = self._get_patch_or_404(patch_id)
        course = self._get_course_or_404(patch.course_id)
        if patch.status == PatchStatus.PROPOSED and course.markdown != patch.base_markdown:
            stale = patch.model_copy(update={"status": PatchStatus.STALE})
            self._patch_repository.update(stale)
            return stale
        return patch

    def apply_patch(self, patch_id: str, owner_feedback: str | None = None) -> DocumentPatch:
        def apply() -> DocumentPatch:
            patch = self._get_patch_or_404(patch_id)
            course = self._get_course_or_404(patch.course_id)
            self._ensure_proposed(patch)
            if course.markdown != patch.base_markdown:
                stale = patch.model_copy(update={"status": PatchStatus.STALE})
                self._patch_repository.update(stale)
                raise AppError(
                    "patch_not_proposed",
                    "Patch is no longer proposed.",
                    status_code=409,
                    current_status=PatchStatus.STALE.value,
                )

            updated_course = course.model_copy(
                update={
                    "markdown": patch.patched_markdown,
                    "version": course.version + 1,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
            applied = patch.model_copy(
                update={
                    "status": PatchStatus.APPLIED,
                    "owner_feedback": owner_feedback,
                }
            )
            self._course_repository.update(updated_course)
            self._patch_repository.update(applied)
            return applied

        return self._run_transaction(apply)

    def reject_patch(self, patch_id: str, owner_feedback: str | None = None) -> DocumentPatch:
        def reject() -> DocumentPatch:
            patch = self._get_patch_or_404(patch_id)
            self._ensure_proposed(patch)
            course = self._get_course_or_404(patch.course_id)
            if course.markdown != patch.base_markdown:
                stale = patch.model_copy(update={"status": PatchStatus.STALE})
                self._patch_repository.update(stale)
                raise AppError(
                    "patch_not_proposed",
                    "Patch is no longer proposed.",
                    status_code=409,
                    current_status=PatchStatus.STALE.value,
                )

            rejected = patch.model_copy(
                update={
                    "status": PatchStatus.REJECTED,
                    "owner_feedback": owner_feedback,
                }
            )
            self._patch_repository.update(rejected)
            return rejected

        return self._run_transaction(reject)

    def _run_transaction(self, callback: Callable[[], T]) -> T:
        return self._firestore_client.run_transaction(callback)

    def _get_patch_or_404(self, patch_id: str) -> DocumentPatch:
        patch = self._patch_repository.get(patch_id)
        if patch is None:
            raise AppError("patch_not_found", "Patch was not found.", status_code=404)
        return patch

    def _get_course_or_404(self, course_id: str) -> Course:
        course = self._course_repository.get(course_id)
        if course is None:
            raise AppError("course_not_found", "Course was not found.", status_code=404)
        return course

    def _ensure_proposed(self, patch: DocumentPatch) -> None:
        if patch.status != PatchStatus.PROPOSED:
            raise AppError(
                "patch_not_proposed",
                "Patch is no longer proposed.",
                status_code=409,
                current_status=patch.status.value,
            )
