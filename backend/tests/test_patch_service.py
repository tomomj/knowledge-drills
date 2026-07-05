import pytest

from app.errors import AppError
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import CourseRepository, PatchRepository
from app.schemas import Course, DocumentPatch, PatchStatus
from app.services.patch_service import PatchService


def _service() -> tuple[PatchService, CourseRepository, PatchRepository]:
    client = InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    patch_repository = PatchRepository(client)
    return (
        PatchService(course_repository, patch_repository, client),
        course_repository,
        patch_repository,
    )


def _patch(status: PatchStatus = PatchStatus.PROPOSED) -> DocumentPatch:
    return DocumentPatch(
        id="patch-1",
        course_id="course-1",
        drill_run_id="drill-1",
        status=status,
        base_markdown="# Before",
        patched_markdown="# After",
        patch_summary="更新",
        diff_text="--- before",
    )


def test_get_patch_marks_proposed_patch_stale_when_course_changed() -> None:
    service, course_repository, patch_repository = _service()
    course_repository.create(Course(id="course-1", title="講座", markdown="# Changed"))
    patch_repository.create(_patch())

    patch = service.get_patch("patch-1")
    saved = patch_repository.get("patch-1")

    assert patch.status == "stale"
    assert saved is not None
    assert saved.status == "stale"


def test_apply_patch_updates_course_and_patch_in_transaction() -> None:
    service, course_repository, patch_repository = _service()
    course_repository.create(Course(id="course-1", title="講座", markdown="# Before"))
    patch_repository.create(_patch())

    patch = service.apply_patch("patch-1", owner_feedback="LGTM")

    course = course_repository.get("course-1")
    assert course is not None
    assert course.markdown == "# After"
    assert course.version == 2
    assert patch.status == "applied"
    assert patch.owner_feedback == "LGTM"


def test_reject_patch_saves_feedback_without_changing_course() -> None:
    service, course_repository, patch_repository = _service()
    course_repository.create(Course(id="course-1", title="講座", markdown="# Before"))
    patch_repository.create(_patch())

    patch = service.reject_patch("patch-1", owner_feedback="不要")

    course = course_repository.get("course-1")
    assert course is not None
    assert course.markdown == "# Before"
    assert patch.status == "rejected"
    assert patch.owner_feedback == "不要"


def test_apply_reject_non_proposed_patch_is_rejected_with_current_status() -> None:
    service, course_repository, patch_repository = _service()
    course_repository.create(Course(id="course-1", title="講座", markdown="# Before"))
    patch_repository.create(_patch(status=PatchStatus.APPLIED))

    with pytest.raises(AppError) as exc_info:
        service.reject_patch("patch-1", owner_feedback="遅い")

    assert exc_info.value.code == "patch_not_proposed"
    assert exc_info.value.current_status == "applied"
