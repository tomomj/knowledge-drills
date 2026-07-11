from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.errors import AppError
from app.repositories.firestore_client import (
    DocumentAlreadyExists,
    DocumentNotFound,
    InMemoryFirestoreClient,
)
from app.repositories.repositories import (
    AnalysisExecutionRepository,
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
    ShareTokenRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas import (
    AnalysisOrigin,
    AnalysisStepStatus,
    AnalysisTimelineItem,
    AnswerStatus,
    AnswerSubmission,
    Course,
    CourseScoreTrendPoint,
    DocumentPatch,
    DrillRun,
    DrillRunStatus,
    PatchStatus,
    UserProfile,
)


class CountingFirestoreClient(InMemoryFirestoreClient):
    def __init__(self) -> None:
        super().__init__()
        self.update_count = 0

    def update_document(
        self,
        collection: str,
        document_id: str,
        data: dict[str, object],
    ) -> None:
        self.update_count += 1
        super().update_document(collection, document_id, data)


class ReadOrderFirestoreClient(InMemoryFirestoreClient):
    def __init__(self) -> None:
        super().__init__()
        self.operations: list[tuple[str, str]] = []

    def get_document(self, collection: str, document_id: str) -> dict[str, object] | None:
        self.operations.append(("get", collection))
        return super().get_document(collection, document_id)

    def list_documents_by_field(
        self,
        collection: str,
        field_name: str,
        field_value: object,
    ) -> list[dict[str, object]]:
        self.operations.append(("list", collection))
        return super().list_documents_by_field(collection, field_name, field_value)

    def update_document(
        self,
        collection: str,
        document_id: str,
        data: dict[str, object],
    ) -> None:
        self.operations.append(("update", collection))
        super().update_document(collection, document_id, data)


class FailCourseCompletionFirestoreClient(InMemoryFirestoreClient):
    def __init__(self) -> None:
        super().__init__()
        self.fail_course_update = False

    def update_document(
        self,
        collection: str,
        document_id: str,
        data: dict[str, object],
    ) -> None:
        if self.fail_course_update and collection == CourseRepository.collection:
            raise RuntimeError("injected course completion failure")
        super().update_document(collection, document_id, data)


def create_drill_run_without_analyzed_answer_count(
    client: InMemoryFirestoreClient,
    drill_run: DrillRun,
) -> None:
    client.create_document(
        DrillRepository.collection,
        drill_run.id,
        drill_run.model_dump(
            mode="json",
            by_alias=True,
            exclude={"analyzed_answer_count"},
        ),
    )


def create_manual_claim_fixture(
    *,
    status: DrillRunStatus = DrillRunStatus.READY,
    error_message: str | None = None,
) -> tuple[
    InMemoryFirestoreClient,
    AnalysisExecutionRepository,
    CourseRepository,
    DrillRepository,
    AnswerRepository,
]:
    client = InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    course_repository.create(
        Course(
            id="course-1",
            owner_user_id="owner-1",
            title="講座",
            markdown="# Body",
            latest_drill_run_id="older-drill",
            latest_drill_status=DrillRunStatus.ANALYZED,
            answer_count=99,
        )
    )
    drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=status,
            error_message=error_message,
            latest_patch_id="old-patch",
        )
    )
    return (
        client,
        AnalysisExecutionRepository(client),
        course_repository,
        drill_repository,
        answer_repository,
    )


def create_auto_claim_fixture(
    *,
    target_status: DrillRunStatus = DrillRunStatus.READY,
    target_course_version: int = 2,
    owner_user_id: str | None = "owner-1",
    scored_answer_count: int = 5,
    total_score: int = 0,
    client: InMemoryFirestoreClient | None = None,
) -> tuple[
    InMemoryFirestoreClient,
    AnalysisExecutionRepository,
    CourseRepository,
    DrillRepository,
    AnswerRepository,
    PatchRepository,
]:
    client = client or InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    patch_repository = PatchRepository(client)
    course_repository.create(
        Course(
            id="course-1",
            owner_user_id=owner_user_id,
            title="講座",
            markdown="# Body",
            version=2,
            latest_drill_run_id="older-drill",
            latest_drill_status=DrillRunStatus.ANALYZED,
            answer_count=99,
        )
    )
    drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            course_version=target_course_version,
            status=target_status,
            latest_patch_id="old-patch",
        )
    )
    for index in range(scored_answer_count):
        answer_repository.create_submission(
            AnswerSubmission(
                id=f"answer-{index}",
                drill_run_id="drill-1",
                learner_name="受講者",
                status=AnswerStatus.GRADED,
                answers={"q1": "回答"},
                total_score=total_score,
                max_score=4,
            )
        )
    return (
        client,
        AnalysisExecutionRepository(client),
        course_repository,
        drill_repository,
        answer_repository,
        patch_repository,
    )


def make_completion_patch(
    *, analysis_origin: AnalysisOrigin = AnalysisOrigin.MANUAL
) -> DocumentPatch:
    return DocumentPatch(
        id="patch-completed",
        course_id="caller-course",
        drill_run_id="caller-drill",
        status=PatchStatus.PROPOSED,
        base_markdown="# Before",
        patched_markdown="# After",
        patch_summary="教材を改善",
        diff_text="--- before\n+++ after",
        analysis_origin=analysis_origin,
    )


def completed_timeline() -> list[AnalysisTimelineItem]:
    return [
        AnalysisTimelineItem(
            id="create_patch",
            title="修正案を作成",
            status=AnalysisStepStatus.COMPLETED,
            summary="完了",
        )
    ]


def test_complete_analysis_atomically_persists_patch_drill_and_course_summary() -> None:
    client, repository, courses, drills, answers, patches = create_auto_claim_fixture()
    claim = repository.claim_auto_analysis("drill-1")
    assert claim is not None
    answers.create_submission(
        AnswerSubmission(
            id="later-answer",
            drill_run_id="drill-1",
            learner_name="後着回答",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=0,
            max_score=4,
        )
    )
    transaction_count = client.transaction_count

    completed = repository.complete_analysis(claim, completed_timeline(), make_completion_patch())

    assert completed is not None
    assert completed.course_id == claim.course_id
    assert completed.drill_run_id == claim.drill_run_id
    assert completed.analysis_origin is AnalysisOrigin.AUTOMATIC
    assert patches.get(completed.id) == completed
    saved_drill = drills.get(claim.drill_run_id)
    assert saved_drill is not None
    assert saved_drill.status is DrillRunStatus.ANALYZED
    assert saved_drill.error_message is None
    assert saved_drill.analysis_timeline == completed_timeline()
    assert saved_drill.analysis_origin is AnalysisOrigin.AUTOMATIC
    assert saved_drill.analyzed_answer_count == 5
    assert saved_drill.auto_analyzed_scored_answer_count == 5
    assert saved_drill.latest_patch_id == completed.id
    saved_course = courses.get(claim.course_id)
    assert saved_course is not None
    assert saved_course.latest_drill_run_id == claim.drill_run_id
    assert saved_course.latest_drill_status is DrillRunStatus.ANALYZED
    assert saved_course.latest_patch_id == completed.id
    assert saved_course.latest_patch_status is PatchStatus.PROPOSED
    assert saved_course.answer_count == 5
    assert client.transaction_count == transaction_count + 1


def test_complete_analysis_without_patch_advances_snapshot_and_preserves_course_patch() -> None:
    client, repository, courses, drills, _answers, patches = create_auto_claim_fixture()
    claim = repository.claim_auto_analysis("drill-1")
    assert claim is not None
    client.update_document(
        CourseRepository.collection,
        claim.course_id,
        {"latestPatchId": "older-patch", "latestPatchStatus": PatchStatus.PROPOSED.value},
    )

    completed = repository.complete_analysis(claim, completed_timeline(), None)

    assert completed is None
    assert patches.list_by_course(claim.course_id) == []
    saved_drill = drills.get(claim.drill_run_id)
    assert saved_drill is not None
    assert saved_drill.status is DrillRunStatus.ANALYZED
    assert saved_drill.analyzed_answer_count == claim.snapshot_agent_answer_count
    assert saved_drill.auto_analyzed_scored_answer_count == claim.snapshot_scored_answer_count
    assert saved_drill.latest_patch_id is None
    saved_course = courses.get(claim.course_id)
    assert saved_course is not None
    assert saved_course.latest_drill_status is DrillRunStatus.ANALYZED
    assert saved_course.latest_patch_id == "older-patch"
    assert saved_course.latest_patch_status is PatchStatus.PROPOSED


def test_complete_analysis_never_regresses_either_watermark() -> None:
    client, repository, _courses, drills, _answers, _patches = create_auto_claim_fixture()
    claim = repository.claim_auto_analysis("drill-1")
    assert claim is not None
    client.update_document(
        DrillRepository.collection,
        claim.drill_run_id,
        {"analyzedAnswerCount": 8, "autoAnalyzedScoredAnswerCount": 7},
    )

    repository.complete_analysis(claim, completed_timeline(), None)

    saved_drill = drills.get(claim.drill_run_id)
    assert saved_drill is not None
    assert saved_drill.analyzed_answer_count == 8
    assert saved_drill.auto_analyzed_scored_answer_count == 7


def test_complete_manual_analysis_keeps_agent_and_scored_watermarks_separate() -> None:
    _client, repository, _courses, drills, answers = create_manual_claim_fixture()
    for answer in (
        AnswerSubmission(
            id="scored",
            drill_run_id="drill-1",
            learner_name="採点済み",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=1,
            max_score=4,
        ),
        AnswerSubmission(
            id="missing-score",
            drill_run_id="drill-1",
            learner_name="スコア欠損",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
        ),
    ):
        answers.create_submission(answer)
    claim = repository.claim_manual_analysis("drill-1", "owner-1")

    completed = repository.complete_analysis(
        claim,
        completed_timeline(),
        make_completion_patch(analysis_origin=AnalysisOrigin.AUTOMATIC),
    )

    assert completed is not None
    assert completed.analysis_origin is AnalysisOrigin.MANUAL
    saved_drill = drills.get(claim.drill_run_id)
    assert saved_drill is not None
    assert saved_drill.analysis_origin is AnalysisOrigin.MANUAL
    assert saved_drill.analyzed_answer_count == 2
    assert saved_drill.auto_analyzed_scored_answer_count == 1


def test_complete_analysis_rejects_changed_course_version_without_consuming_claim() -> None:
    client, repository, _courses, _drills, _answers, _patches = create_auto_claim_fixture()
    claim = repository.claim_auto_analysis("drill-1")
    assert claim is not None
    client.update_document(CourseRepository.collection, claim.course_id, {"version": 3})
    drill_before = client.get_document(DrillRepository.collection, claim.drill_run_id)
    course_before = client.get_document(CourseRepository.collection, claim.course_id)

    with pytest.raises(AppError) as exc_info:
        repository.complete_analysis(claim, completed_timeline(), make_completion_patch())

    assert exc_info.value.code == "analysis_course_version_changed"
    assert client.get_document(PatchRepository.collection, "patch-completed") is None
    assert client.get_document(DrillRepository.collection, claim.drill_run_id) == drill_before
    assert client.get_document(CourseRepository.collection, claim.course_id) == course_before


def test_complete_analysis_rejects_claim_state_mismatch_without_writes() -> None:
    client, repository, _courses, _drills, _answers, _patches = create_auto_claim_fixture()
    claim = repository.claim_auto_analysis("drill-1")
    assert claim is not None
    client.update_document(
        DrillRepository.collection,
        claim.drill_run_id,
        {"status": DrillRunStatus.READY.value},
    )
    drill_before = client.get_document(DrillRepository.collection, claim.drill_run_id)
    course_before = client.get_document(CourseRepository.collection, claim.course_id)

    with pytest.raises(AppError) as exc_info:
        repository.complete_analysis(claim, completed_timeline(), make_completion_patch())

    assert exc_info.value.code == "analysis_claim_conflict"
    assert client.get_document(PatchRepository.collection, "patch-completed") is None
    assert client.get_document(DrillRepository.collection, claim.drill_run_id) == drill_before
    assert client.get_document(CourseRepository.collection, claim.course_id) == course_before


def test_complete_analysis_rolls_back_patch_drill_and_course_on_failure() -> None:
    fault_client = FailCourseCompletionFirestoreClient()
    client, repository, _courses, _drills, _answers, _patches = create_auto_claim_fixture(
        client=fault_client
    )
    claim = repository.claim_auto_analysis("drill-1")
    assert claim is not None
    drill_before = client.get_document(DrillRepository.collection, claim.drill_run_id)
    course_before = client.get_document(CourseRepository.collection, claim.course_id)
    fault_client.fail_course_update = True

    with pytest.raises(RuntimeError, match="injected course completion failure"):
        repository.complete_analysis(claim, completed_timeline(), make_completion_patch())

    assert client.get_document(PatchRepository.collection, "patch-completed") is None
    assert client.get_document(DrillRepository.collection, claim.drill_run_id) == drill_before
    assert client.get_document(CourseRepository.collection, claim.course_id) == course_before


def test_auto_analysis_claim_snapshots_only_scored_answers_and_marks_automatic() -> None:
    (
        client,
        repository,
        course_repository,
        drill_repository,
        answer_repository,
        _patch_repository,
    ) = create_auto_claim_fixture()
    answer_repository.create_submission(
        AnswerSubmission(
            id="missing-score",
            drill_run_id="drill-1",
            learner_name="受講者",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
        )
    )
    answer_repository.create_submission(
        AnswerSubmission(
            id="grading",
            drill_run_id="drill-1",
            learner_name="受講者",
            status=AnswerStatus.GRADING,
            answers={"q1": "回答"},
            total_score=0,
            max_score=4,
        )
    )

    claim = repository.claim_auto_analysis("drill-1")

    assert claim is not None
    assert claim.course_id == "course-1"
    assert claim.drill_run_id == "drill-1"
    assert claim.owner_user_id == "owner-1"
    assert claim.course_version == 2
    assert claim.answer_ids == tuple(f"answer-{index}" for index in range(5))
    assert claim.snapshot_agent_answer_count == 5
    assert claim.snapshot_scored_answer_count == 5
    assert claim.origin is AnalysisOrigin.AUTOMATIC

    saved_drill = drill_repository.get("drill-1")
    saved_course = course_repository.get("course-1")
    assert saved_drill is not None
    assert saved_drill.status is DrillRunStatus.ANALYZING
    assert saved_drill.error_message is None
    assert saved_drill.analysis_origin is AnalysisOrigin.AUTOMATIC
    assert saved_drill.latest_patch_id is None
    assert saved_drill.analysis_timeline[0].status is AnalysisStepStatus.RUNNING
    assert all(
        item.status is AnalysisStepStatus.PENDING
        for item in saved_drill.analysis_timeline[1:]
    )
    assert saved_course is not None
    assert saved_course.latest_drill_run_id == "drill-1"
    assert saved_course.latest_drill_status is DrillRunStatus.ANALYZING
    assert saved_course.answer_count == 7
    assert client.transaction_count == 1


@pytest.mark.parametrize(
    ("fixture_overrides", "expected_status"),
    [
        ({"target_course_version": 1}, DrillRunStatus.READY),
        ({"scored_answer_count": 4}, DrillRunStatus.READY),
        ({"total_score": 4}, DrillRunStatus.READY),
        ({"target_status": DrillRunStatus.ANALYZING}, DrillRunStatus.ANALYZING),
        ({"target_status": DrillRunStatus.GENERATING}, DrillRunStatus.GENERATING),
        ({"owner_user_id": None}, DrillRunStatus.READY),
    ],
)
def test_auto_analysis_claim_guard_is_a_write_free_no_op(
    fixture_overrides: dict[str, object],
    expected_status: DrillRunStatus,
) -> None:
    client, repository, course_repository, drill_repository, *_rest = (
        create_auto_claim_fixture(**fixture_overrides)  # type: ignore[arg-type]
    )
    drill_before = client.get_document(DrillRepository.collection, "drill-1")
    course_before = client.get_document(CourseRepository.collection, "course-1")

    claim = repository.claim_auto_analysis("drill-1")

    assert claim is None
    assert client.get_document(DrillRepository.collection, "drill-1") == drill_before
    assert client.get_document(CourseRepository.collection, "course-1") == course_before
    saved_drill = drill_repository.get("drill-1")
    saved_course = course_repository.get("course-1")
    assert saved_drill is not None and saved_drill.status is expected_status
    assert saved_course is not None
    assert saved_course.latest_drill_run_id == "older-drill"


def test_auto_analysis_claim_is_blocked_by_same_course_proposed_patch_only() -> None:
    client, repository, _course_repository, drill_repository, _answers, patches = (
        create_auto_claim_fixture()
    )
    patches.create(
        DocumentPatch(
            id="patch-1",
            course_id="course-1",
            drill_run_id="other-drill",
            status=PatchStatus.PROPOSED,
            base_markdown="# old",
            patched_markdown="# new",
            patch_summary="改善",
            diff_text="diff",
        )
    )
    before = client.get_document(DrillRepository.collection, "drill-1")

    assert repository.claim_auto_analysis("drill-1") is None
    assert client.get_document(DrillRepository.collection, "drill-1") == before
    saved = drill_repository.get("drill-1")
    assert saved is not None and saved.latest_patch_id == "old-patch"


def test_auto_analysis_claim_ignores_proposed_patch_from_another_course() -> None:
    client, repository, *_rest = create_auto_claim_fixture()
    client.create_document(
        PatchRepository.collection,
        "other-course-patch",
        DocumentPatch(
            id="other-course-patch",
            course_id="course-2",
            drill_run_id="drill-2",
            status=PatchStatus.PROPOSED,
            base_markdown="# old",
            patched_markdown="# new",
            patch_summary="改善",
            diff_text="diff",
        ).model_dump(mode="json", by_alias=True),
    )

    claim = repository.claim_auto_analysis("drill-1")

    assert claim is not None
    assert claim.origin is AnalysisOrigin.AUTOMATIC


def test_auto_analysis_claim_uses_scored_watermark_for_five_answer_threshold() -> None:
    client, repository, _courses, drills, *_rest = create_auto_claim_fixture(
        scored_answer_count=6
    )
    drill = drills.get("drill-1")
    assert drill is not None
    drills.update(
        drill.model_copy(
            update={
                "auto_analyzed_scored_answer_count": 2,
            }
        )
    )
    before = client.get_document(DrillRepository.collection, "drill-1")

    claim = repository.claim_auto_analysis("drill-1")

    assert claim is None
    assert client.get_document(DrillRepository.collection, "drill-1") == before


def test_auto_analysis_claim_reads_full_decision_set_before_writing() -> None:
    recording_client = ReadOrderFirestoreClient()
    client, repository, _courses, drills, answers, *_rest = create_auto_claim_fixture(
        client=recording_client
    )
    drills.create(
        DrillRun(
            id="drill-2",
            course_id="course-1",
            course_version=2,
            status=DrillRunStatus.READY,
        )
    )
    answers.create_submission(
        AnswerSubmission(
            id="other-answer",
            drill_run_id="drill-2",
            learner_name="受講者",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=0,
            max_score=4,
        )
    )
    recording_client.operations.clear()

    claim = repository.claim_auto_analysis("drill-1")

    assert claim is not None
    first_write = recording_client.operations.index(("update", DrillRepository.collection))
    assert recording_client.operations[:first_write] == [
        ("get", DrillRepository.collection),
        ("get", CourseRepository.collection),
        ("list", DrillRepository.collection),
        ("list", AnswerRepository.collection),
        ("list", AnswerRepository.collection),
        ("list", PatchRepository.collection),
    ]
    assert recording_client.operations[first_write:] == [
        ("update", DrillRepository.collection),
        ("update", CourseRepository.collection),
    ]
    assert client is recording_client


def test_auto_analysis_second_claim_is_no_op_without_changing_first_claim_state() -> None:
    client, repository, course_repository, drill_repository, *_rest = (
        create_auto_claim_fixture()
    )
    first = repository.claim_auto_analysis("drill-1")
    drill_after_first = client.get_document(DrillRepository.collection, "drill-1")
    course_after_first = client.get_document(CourseRepository.collection, "course-1")

    second = repository.claim_auto_analysis("drill-1")

    assert first is not None
    assert second is None
    assert client.get_document(DrillRepository.collection, "drill-1") == drill_after_first
    assert client.get_document(CourseRepository.collection, "course-1") == course_after_first
    saved_drill = drill_repository.get("drill-1")
    saved_course = course_repository.get("course-1")
    assert saved_drill is not None and saved_drill.analysis_origin is AnalysisOrigin.AUTOMATIC
    assert saved_course is not None


def test_manual_claim_prevents_auto_claim_without_changing_manual_state() -> None:
    client, repository, _course_repository, drill_repository, *_rest = (
        create_auto_claim_fixture()
    )
    manual = repository.claim_manual_analysis("drill-1", "owner-1")
    after_manual = client.get_document(DrillRepository.collection, "drill-1")

    automatic = repository.claim_auto_analysis("drill-1")

    assert manual.origin is AnalysisOrigin.MANUAL
    assert automatic is None
    assert client.get_document(DrillRepository.collection, "drill-1") == after_manual
    saved = drill_repository.get("drill-1")
    assert saved is not None and saved.analysis_origin is AnalysisOrigin.MANUAL


def test_manual_analysis_claim_snapshots_all_graded_answers_and_scored_count_separately() -> None:
    client, repository, course_repository, drill_repository, answer_repository = (
        create_manual_claim_fixture()
    )
    for answer in (
        AnswerSubmission(
            id="scored",
            drill_run_id="drill-1",
            learner_name="採点済み",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=1,
            max_score=4,
        ),
        AnswerSubmission(
            id="missing-score",
            drill_run_id="drill-1",
            learner_name="スコア欠損",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
        ),
        AnswerSubmission(
            id="grading",
            drill_run_id="drill-1",
            learner_name="採点中",
            status=AnswerStatus.GRADING,
            answers={"q1": "回答"},
            total_score=1,
            max_score=4,
        ),
    ):
        answer_repository.create_submission(answer)

    claim = repository.claim_manual_analysis("drill-1", "owner-1")

    assert claim.course_id == "course-1"
    assert claim.drill_run_id == "drill-1"
    assert claim.owner_user_id == "owner-1"
    assert claim.course_version == 1
    assert claim.answer_ids == ("scored", "missing-score")
    assert claim.snapshot_agent_answer_count == 2
    assert claim.snapshot_scored_answer_count == 1
    assert claim.origin is AnalysisOrigin.MANUAL

    saved_drill = drill_repository.get("drill-1")
    saved_course = course_repository.get("course-1")
    assert saved_drill is not None
    assert saved_drill.status is DrillRunStatus.ANALYZING
    assert saved_drill.error_message is None
    assert saved_drill.analysis_origin is AnalysisOrigin.MANUAL
    assert saved_drill.latest_patch_id is None
    assert [item.id for item in saved_drill.analysis_timeline] == [
        "collect_answers",
        "detect_failure_patterns",
        "match_course_evidence",
        "decide_patch_strategy",
        "create_patch",
    ]
    assert saved_drill.analysis_timeline[0].status is AnalysisStepStatus.RUNNING
    assert all(
        item.status is AnalysisStepStatus.PENDING
        for item in saved_drill.analysis_timeline[1:]
    )
    assert saved_course is not None
    assert saved_course.latest_drill_run_id == "drill-1"
    assert saved_course.latest_drill_status is DrillRunStatus.ANALYZING
    assert saved_course.answer_count == 3
    assert client.transaction_count == 1


@pytest.mark.parametrize(
    ("status", "error_message"),
    [
        (DrillRunStatus.GENERATING, None),
        (DrillRunStatus.ANALYZING, None),
        (DrillRunStatus.FAILED, "drill generation failed"),
    ],
)
def test_manual_analysis_claim_preserves_state_guard(
    status: DrillRunStatus,
    error_message: str | None,
) -> None:
    _client, repository, _course_repository, _drill_repository, answer_repository = (
        create_manual_claim_fixture(status=status, error_message=error_message)
    )
    answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            drill_run_id="drill-1",
            learner_name="受講者",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
        )
    )

    with pytest.raises(AppError) as exc_info:
        repository.claim_manual_analysis("drill-1", "owner-1")

    assert exc_info.value.code == "drill_not_analyzable"
    assert exc_info.value.status_code == 409


@pytest.mark.parametrize(
    ("status", "error_message"),
    [
        (DrillRunStatus.ANALYZED, None),
        (DrillRunStatus.FAILED, "analysis failed"),
    ],
)
def test_manual_analysis_claim_preserves_retryable_states(
    status: DrillRunStatus,
    error_message: str | None,
) -> None:
    _client, repository, _course_repository, drill_repository, answer_repository = (
        create_manual_claim_fixture(status=status, error_message=error_message)
    )
    answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            drill_run_id="drill-1",
            learner_name="受講者",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
        )
    )

    repository.claim_manual_analysis("drill-1", "owner-1")

    saved = drill_repository.get("drill-1")
    assert saved is not None
    assert saved.status is DrillRunStatus.ANALYZING
    assert saved.error_message is None


def test_manual_analysis_second_claim_conflicts_without_changing_snapshot() -> None:
    _client, repository, _course_repository, drill_repository, answer_repository = (
        create_manual_claim_fixture()
    )
    answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            drill_run_id="drill-1",
            learner_name="受講者",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
        )
    )
    first_claim = repository.claim_manual_analysis("drill-1", "owner-1")

    with pytest.raises(AppError) as exc_info:
        repository.claim_manual_analysis("drill-1", "owner-1")

    assert exc_info.value.code == "drill_not_analyzable"
    assert exc_info.value.status_code == 409
    assert first_claim.answer_ids == ("answer-1",)
    saved = drill_repository.get("drill-1")
    assert saved is not None
    assert saved.status is DrillRunStatus.ANALYZING


def test_manual_analysis_claim_preserves_owner_not_found_boundary() -> None:
    _client, repository, _course_repository, _drill_repository, answer_repository = (
        create_manual_claim_fixture()
    )
    answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            drill_run_id="drill-1",
            learner_name="受講者",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
        )
    )

    with pytest.raises(AppError) as exc_info:
        repository.claim_manual_analysis("drill-1", "other-owner")

    assert exc_info.value.code == "drill_run_not_found"
    assert exc_info.value.status_code == 404


def test_manual_analysis_claim_requires_a_graded_answer() -> None:
    _client, repository, _course_repository, _drill_repository, answer_repository = (
        create_manual_claim_fixture()
    )
    answer_repository.create_submission(
        AnswerSubmission(
            id="grading",
            drill_run_id="drill-1",
            learner_name="受講者",
            status=AnswerStatus.GRADING,
            answers={"q1": "回答"},
        )
    )

    with pytest.raises(AppError) as exc_info:
        repository.claim_manual_analysis("drill-1", "owner-1")

    assert exc_info.value.code == "no_graded_answers"


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


def test_share_token_repository_updates_target_and_open_state() -> None:
    client = InMemoryFirestoreClient()
    repository = ShareTokenRepository(client)
    repository.reserve(
        "token-1",
        drill_run_id="drill-1",
        course_id="course-1",
        created_at="2026-07-11T00:00:00+00:00",
    )

    repository.close("token-1", "2026-07-11T01:00:00+00:00")
    closed = repository.get("token-1")
    assert closed is not None
    assert closed.closed_at == "2026-07-11T01:00:00+00:00"

    repository.point_to_drill("token-1", "drill-2", "course-1")
    repository.reopen("token-1")
    reopened = repository.get("token-1")
    assert reopened is not None
    assert reopened.drill_run_id == "drill-2"
    assert reopened.course_id == "course-1"
    assert reopened.closed_at is None


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


def test_drill_repository_initializes_analyzed_answer_count_once_under_concurrency() -> None:
    client = CountingFirestoreClient()
    repository = DrillRepository(client)
    create_drill_run_without_analyzed_answer_count(
        client,
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.ANALYZED)
    )

    worker_count = 8
    ready = Barrier(worker_count)

    def initialize(baseline: int) -> None:
        ready.wait()
        repository.initialize_analyzed_answer_count("drill-1", baseline)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [
            executor.submit(initialize, baseline) for baseline in range(worker_count)
        ]
        for future in futures:
            future.result()

    saved = repository.get("drill-1")
    assert saved is not None
    assert saved.analyzed_answer_count in range(worker_count)
    assert client.update_count == 1


def test_drill_repository_initializes_explicit_null_analyzed_answer_count() -> None:
    client = InMemoryFirestoreClient()
    repository = DrillRepository(client)
    repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=DrillRunStatus.ANALYZED,
            analyzed_answer_count=None,
        )
    )

    repository.initialize_analyzed_answer_count("drill-1", 4)

    saved = repository.get("drill-1")
    assert saved is not None
    assert saved.analyzed_answer_count == 4


def test_drill_repository_initialization_is_noop_for_analyzing_or_recorded_run() -> None:
    client = CountingFirestoreClient()
    repository = DrillRepository(client)
    create_drill_run_without_analyzed_answer_count(
        client,
        DrillRun(id="analyzing", course_id="course-1", status=DrillRunStatus.ANALYZING)
    )
    repository.create(
        DrillRun(
            id="recorded",
            course_id="course-1",
            status=DrillRunStatus.ANALYZED,
            analyzed_answer_count=0,
        )
    )

    repository.initialize_analyzed_answer_count("analyzing", 3)
    repository.initialize_analyzed_answer_count("recorded", 2)

    analyzing = repository.get("analyzing")
    recorded = repository.get("recorded")
    assert analyzing is not None
    assert analyzing.analyzed_answer_count is None
    assert recorded is not None
    assert recorded.analyzed_answer_count == 0
    assert client.update_count == 0


def test_drill_repository_initialization_updates_only_analyzed_answer_count() -> None:
    client = InMemoryFirestoreClient()
    repository = DrillRepository(client)
    drill_run = DrillRun(
        id="drill-1",
        course_id="course-1",
        status=DrillRunStatus.ANALYZED,
        analysis_timeline=[
            AnalysisTimelineItem(
                id="analysis",
                title="分析",
                status=AnalysisStepStatus.COMPLETED,
                completed_at="2026-07-11T00:01:00+00:00",
            )
        ],
    )
    create_drill_run_without_analyzed_answer_count(client, drill_run)
    before = client.get_document(repository.collection, drill_run.id)

    repository.initialize_analyzed_answer_count(drill_run.id, 4)

    after = client.get_document(repository.collection, drill_run.id)
    assert before is not None
    assert after == {**before, "analyzedAnswerCount": 4}


def test_drill_repository_initialization_preserves_completion_update_ordering() -> None:
    client = InMemoryFirestoreClient()
    repository = DrillRepository(client)
    create_drill_run_without_analyzed_answer_count(
        client,
        DrillRun(id="initialize-first", course_id="course-1", status=DrillRunStatus.ANALYZED)
    )
    repository.create(
        DrillRun(id="completion-first", course_id="course-1", status=DrillRunStatus.ANALYZED)
    )

    repository.initialize_analyzed_answer_count("initialize-first", 3)
    repository.update(
        DrillRun(
            id="initialize-first",
            course_id="course-1",
            status=DrillRunStatus.ANALYZED,
            analyzed_answer_count=5,
        )
    )
    repository.update(
        DrillRun(
            id="completion-first",
            course_id="course-1",
            status=DrillRunStatus.ANALYZED,
            analyzed_answer_count=5,
        )
    )
    repository.initialize_analyzed_answer_count("completion-first", 3)

    initialize_first = repository.get("initialize-first")
    completion_first = repository.get("completion-first")
    assert initialize_first is not None
    assert initialize_first.analyzed_answer_count == 5
    assert completion_first is not None
    assert completion_first.analyzed_answer_count == 5


def test_drill_repository_update_never_decreases_analyzed_answer_count() -> None:
    client = InMemoryFirestoreClient()
    repository = DrillRepository(client)
    create_drill_run_without_analyzed_answer_count(
        client,
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.ANALYZED),
    )
    stale = repository.get("drill-1")
    assert stale is not None

    repository.initialize_analyzed_answer_count("drill-1", 3)
    repository.update(
        stale.model_copy(
            update={
                "status": DrillRunStatus.ANALYZING,
                "analysis_timeline": [
                    AnalysisTimelineItem(
                        id="analysis",
                        title="分析",
                        status=AnalysisStepStatus.RUNNING,
                    )
                ],
            }
        )
    )

    after_stale_update = repository.get("drill-1")
    assert after_stale_update is not None
    assert after_stale_update.status == DrillRunStatus.ANALYZING
    assert after_stale_update.analysis_timeline[0].status == AnalysisStepStatus.RUNNING
    assert after_stale_update.analyzed_answer_count == 3

    repository.update(
        after_stale_update.model_copy(
            update={
                "status": DrillRunStatus.ANALYZED,
                "analyzed_answer_count": 2,
                "analysis_timeline": [
                    AnalysisTimelineItem(
                        id="analysis",
                        title="分析",
                        status=AnalysisStepStatus.COMPLETED,
                    )
                ],
            }
        )
    )
    after_lower_update = repository.get("drill-1")
    assert after_lower_update is not None
    assert after_lower_update.status == DrillRunStatus.ANALYZED
    assert after_lower_update.analysis_timeline[0].status == AnalysisStepStatus.COMPLETED
    assert after_lower_update.analyzed_answer_count == 3

    repository.update(after_lower_update.model_copy(update={"analyzed_answer_count": 5}))
    after_higher_update = repository.get("drill-1")
    assert after_higher_update is not None
    assert after_higher_update.analyzed_answer_count == 5


def test_drill_repository_initialization_validates_baseline_and_propagates_missing() -> None:
    client = InMemoryFirestoreClient()
    repository = DrillRepository(client)

    with pytest.raises(ValueError, match="baseline"):
        repository.initialize_analyzed_answer_count("missing", -1)
    with pytest.raises(DocumentNotFound):
        repository.initialize_analyzed_answer_count("missing", 0)


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
