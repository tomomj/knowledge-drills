import pytest

from app.repositories.firestore_client import DocumentAlreadyExists, InMemoryFirestoreClient
from app.repositories.repositories import (
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
    ShareTokenRepository,
)
from app.schemas import AnswerStatus, Course, DocumentPatch, DrillRun, DrillRunStatus, PatchStatus


def test_course_repository_creates_and_updates_course() -> None:
    client = InMemoryFirestoreClient()
    repository = CourseRepository(client)
    course = Course(id="course-1", title="講座", markdown="# Body")

    repository.create(course)
    repository.update(course.model_copy(update={"version": 2, "latest_drill_run_id": "drill-1"}))

    saved = repository.get("course-1")
    assert saved is not None
    assert saved.version == 2
    assert saved.latest_drill_run_id == "drill-1"


def test_share_token_repository_uses_create_only_reservation() -> None:
    client = InMemoryFirestoreClient()
    repository = ShareTokenRepository(client)

    repository.reserve("token-1", drill_run_id="drill-1")

    with pytest.raises(DocumentAlreadyExists):
        repository.reserve("token-1", drill_run_id="drill-2")


def test_drill_answer_and_patch_repositories_support_status_updates() -> None:
    client = InMemoryFirestoreClient()
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    patch_repository = PatchRepository(client)

    drill_repository.create(
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.GENERATING)
    )
    answer_repository.create(
        id="answer-1",
        drill_run_id="drill-1",
        learner_name="受講者",
        status=AnswerStatus.GRADING,
        answers={"q1": "回答"},
    )
    patch_repository.create(
        DocumentPatch(
            id="patch-1",
            course_id="course-1",
            drill_run_id="drill-1",
            status=PatchStatus.PROPOSED,
            base_markdown="# Before",
            patched_markdown="# After",
            patch_summary="追記",
            diff_text="--- before",
        )
    )

    drill_repository.update_status("drill-1", DrillRunStatus.READY)
    answer_repository.update_status("answer-1", AnswerStatus.GRADED)
    patch_repository.update_status("patch-1", PatchStatus.APPLIED)

    drill_run = drill_repository.get("drill-1")
    answer = answer_repository.get("answer-1")
    patch = patch_repository.get("patch-1")
    assert drill_run is not None
    assert answer is not None
    assert patch is not None
    assert drill_run.status == "ready"
    assert answer.status == "graded"
    assert patch.status == "applied"


def test_transaction_callback_is_observed_for_patch_decision() -> None:
    client = InMemoryFirestoreClient()
    patch_repository = PatchRepository(client)
    patch_repository.create(
        DocumentPatch(
            id="patch-1",
            course_id="course-1",
            drill_run_id="drill-1",
            status=PatchStatus.PROPOSED,
            base_markdown="# Before",
            patched_markdown="# After",
            patch_summary="追記",
            diff_text="--- before",
        )
    )

    def apply_patch() -> None:
        patch_repository.update_status("patch-1", PatchStatus.REJECTED)

    client.run_transaction(apply_patch)

    assert client.transaction_count == 1
    patch = patch_repository.get("patch-1")
    assert patch is not None
    assert patch.status == "rejected"
