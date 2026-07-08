import pytest

from app.repositories.firestore_client import DocumentAlreadyExists, InMemoryFirestoreClient
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
    Course,
    CourseScoreTrendPoint,
    DocumentPatch,
    DrillRun,
    DrillRunStatus,
    PatchStatus,
    UserProfile,
)


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


def test_course_summary_update_does_not_record_revision() -> None:
    client = InMemoryFirestoreClient()
    repository = CourseRepository(client)
    repository.create(Course(id="course-1", title="講座", markdown="# Body"))

    repository.update_summary(
        "course-1",
        latest_drill_run_id="drill-1",
        latest_drill_status=DrillRunStatus.READY,
        answer_count=2,
        latest_patch_id="patch-1",
        latest_patch_status=PatchStatus.PROPOSED,
    )

    saved = repository.get("course-1")
    revisions = repository.list_revisions("course-1")
    assert saved is not None
    assert saved.latest_drill_run_id == "drill-1"
    assert saved.latest_drill_status == "ready"
    assert saved.answer_count == 2
    assert saved.latest_patch_id == "patch-1"
    assert saved.latest_patch_status == "proposed"
    assert [revision.version for revision in revisions] == [1]


def test_course_repository_updates_score_trend_without_revision() -> None:
    client = InMemoryFirestoreClient()
    repository = CourseRepository(client)
    repository.create(Course(id="course-1", title="講座", markdown="# Body"))

    repository.update_score_trend_point(
        "course-1",
        CourseScoreTrendPoint(course_version=2, average_score=3.0, max_score=4),
    )
    repository.update_score_trend_point(
        "course-1",
        CourseScoreTrendPoint(course_version=1, average_score=2.0, max_score=4),
    )

    saved = repository.get("course-1")
    assert saved is not None
    assert saved.score_trend == [
        CourseScoreTrendPoint(course_version=1, average_score=2.0, max_score=4),
        CourseScoreTrendPoint(course_version=2, average_score=3.0, max_score=4),
    ]
    assert [revision.version for revision in repository.list_revisions("course-1")] == [1]


def test_share_token_repository_uses_create_only_reservation() -> None:
    client = InMemoryFirestoreClient()
    repository = ShareTokenRepository(client)

    repository.reserve("token-1", drill_run_id="drill-1")

    with pytest.raises(DocumentAlreadyExists):
        repository.reserve("token-1", drill_run_id="drill-2")


def test_repositories_delete_documents_and_noop_for_missing() -> None:
    client = InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    patch_repository = PatchRepository(client)
    share_token_repository = ShareTokenRepository(client)

    course_repository.create(Course(id="course-1", title="講座", markdown="# Body"))
    drill_repository.create(
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.READY)
    )
    share_token_repository.reserve("token-1", "drill-1")
    answer_repository.create(
        id="answer-1",
        drill_run_id="drill-1",
        learner_name="受講者",
        status=AnswerStatus.GRADED,
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

    assert [patch.id for patch in patch_repository.list_by_course("course-1")] == ["patch-1"]

    share_token_repository.delete("token-1")
    answer_repository.delete("answer-1")
    drill_repository.delete("drill-1")
    patch_repository.delete("patch-1")
    course_repository.delete_revision("course-1", 1)
    course_repository.delete("course-1")
    share_token_repository.delete("token-1")

    assert share_token_repository.get_drill_run_id("token-1") is None
    assert answer_repository.get("answer-1") is None
    assert drill_repository.get("drill-1") is None
    assert patch_repository.get("patch-1") is None
    assert course_repository.get_revision("course-1", 1) is None
    assert course_repository.get("course-1") is None


def test_user_repository_claims_demo_seeded_without_overwriting_profile() -> None:
    client = InMemoryFirestoreClient()
    repository = UserRepository(client)
    repository.upsert(
        UserProfile(
            uid="owner-1",
            email="owner@example.test",
            display_name="Owner",
            photo_url=None,
            created_at="2026-07-08T00:00:00+00:00",
            last_login_at="2026-07-08T00:00:00+00:00",
        )
    )

    assert repository.claim_demo_seeded("owner-1", "2026-07-08T01:00:00+00:00") is True
    assert repository.claim_demo_seeded("owner-1", "2026-07-08T02:00:00+00:00") is False

    saved = repository.get("owner-1")
    assert saved is not None
    assert saved.email == "owner@example.test"
    assert saved.created_at == "2026-07-08T00:00:00+00:00"
    assert saved.demo_seeded_at == "2026-07-08T01:00:00+00:00"


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
