from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, field
from threading import Barrier, Event, RLock, local
from typing import TypeVar, cast

from app.errors import AppError
from app.repositories.firestore_client import (
    DocumentAlreadyExists,
    DocumentData,
    DocumentNotFound,
    InMemoryFirestoreClient,
)
from app.repositories.repositories import (
    AnalysisExecutionRepository,
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
)
from app.schemas import (
    AnalysisClaim,
    AnalysisOrigin,
    AnalysisStepStatus,
    AnalysisTimelineItem,
    AnswerStatus,
    AnswerSubmission,
    Course,
    DocumentPatch,
    DrillRun,
    DrillRunStatus,
    PatchStatus,
)
from app.services.analysis_service import AnalysisService
from app.services.auto_analysis import AutoAnalysisTrigger

T = TypeVar("T")
_Collections = dict[str, dict[str, DocumentData]]
_DocumentKey = tuple[str, str]


@dataclass
class _TransactionContext:
    collections: _Collections
    start_versions: dict[_DocumentKey, int]
    read_keys: set[_DocumentKey]
    write_keys: set[_DocumentKey]


@dataclass
class _CommitGate:
    first_attempt_ready: Event
    release_first_attempt: Event
    attempts: int = 0
    retry_conflicts: list[set[_DocumentKey]] = field(default_factory=list)


class _TransactionLocal(local):
    context: _TransactionContext | None
    gate: _CommitGate | None

    def __init__(self) -> None:
        self.context = None
        self.gate = None


class _OptimisticFirestoreClient:
    """Document-version retry model for the shared course linearization boundary."""

    def __init__(self) -> None:
        self._collections: _Collections = {}
        self._lock = RLock()
        self._document_versions: dict[_DocumentKey, int] = {}
        self._local = _TransactionLocal()

    def gate_next_transaction(self, gate: _CommitGate) -> None:
        self._local.gate = gate

    def create_document(self, collection: str, document_id: str, data: DocumentData) -> None:
        def create(collections: _Collections) -> None:
            documents = collections.setdefault(collection, {})
            if document_id in documents:
                raise DocumentAlreadyExists(f"{collection}/{document_id} already exists")
            documents[document_id] = deepcopy(data)

        self._write((collection, document_id), create)

    def set_document(self, collection: str, document_id: str, data: DocumentData) -> None:
        self._write(
            (collection, document_id),
            lambda collections: collections.setdefault(collection, {}).__setitem__(
                document_id,
                deepcopy(data),
            ),
        )

    def get_document(self, collection: str, document_id: str) -> DocumentData | None:
        context = self._local.context
        if context is not None:
            context.read_keys.add((collection, document_id))
            document = context.collections.get(collection, {}).get(document_id)
            return deepcopy(document) if document is not None else None
        with self._lock:
            document = self._collections.get(collection, {}).get(document_id)
            return deepcopy(document) if document is not None else None

    def update_document(self, collection: str, document_id: str, data: DocumentData) -> None:
        def update(collections: _Collections) -> None:
            documents = collections.setdefault(collection, {})
            if document_id not in documents:
                raise DocumentNotFound(f"{collection}/{document_id} was not found")
            documents[document_id].update(deepcopy(data))

        self._write((collection, document_id), update)

    def delete_document(self, collection: str, document_id: str) -> None:
        def delete(collections: _Collections) -> None:
            collections.setdefault(collection, {}).pop(document_id, None)

        self._write((collection, document_id), delete)

    def list_documents(self, collection: str) -> list[DocumentData]:
        context = self._local.context
        if context is not None:
            return [
                deepcopy(document) for document in context.collections.get(collection, {}).values()
            ]
        with self._lock:
            return [
                deepcopy(document) for document in self._collections.get(collection, {}).values()
            ]

    def list_documents_by_field(
        self,
        collection: str,
        field_name: str,
        field_value: object,
    ) -> list[DocumentData]:
        return [
            document
            for document in self.list_documents(collection)
            if document.get(field_name) == field_value
        ]

    def run_transaction(self, callback: Callable[[], T]) -> T:
        gate = self._local.gate
        self._local.gate = None
        for _attempt in range(3):
            with self._lock:
                context = _TransactionContext(
                    collections=deepcopy(self._collections),
                    start_versions=self._document_versions.copy(),
                    read_keys=set(),
                    write_keys=set(),
                )
            self._local.context = context
            try:
                result = callback()
            finally:
                self._local.context = None

            if gate is not None:
                gate.attempts += 1
                if gate.attempts == 1:
                    gate.first_attempt_ready.set()
                    if not gate.release_first_attempt.wait(timeout=2):
                        raise AssertionError(
                            "timed out waiting to release first transaction attempt"
                        )

            with self._lock:
                conflict_keys = {
                    key
                    for key in context.read_keys | context.write_keys
                    if self._document_versions.get(key, 0) != context.start_versions.get(key, 0)
                }
                if conflict_keys:
                    if gate is not None:
                        gate.retry_conflicts.append(conflict_keys)
                    continue
                for collection, document_id in context.write_keys:
                    local_document = context.collections.get(collection, {}).get(document_id)
                    if local_document is None:
                        self._collections.setdefault(collection, {}).pop(document_id, None)
                    else:
                        self._collections.setdefault(collection, {})[document_id] = deepcopy(
                            local_document
                        )
                    key = (collection, document_id)
                    self._document_versions[key] = self._document_versions.get(key, 0) + 1
                return result
        raise AssertionError("transaction did not commit after deterministic retry")

    def _write(
        self,
        key: _DocumentKey,
        operation: Callable[[_Collections], None],
    ) -> None:
        context = self._local.context
        if context is not None:
            operation(context.collections)
            context.write_keys.add(key)
            return
        with self._lock:
            operation(self._collections)
            self._document_versions[key] = self._document_versions.get(key, 0) + 1


class _BlockingAnalysisExecutor:
    def __init__(self) -> None:
        self.claims: list[AnalysisClaim] = []
        self.entered = Event()
        self.release = Event()

    def run_claimed_analysis(self, claim: AnalysisClaim) -> DocumentPatch | None:
        self.claims.append(claim)
        self.entered.set()
        if not self.release.wait(timeout=2):
            raise AssertionError("timed out waiting to release analysis executor")
        return None


def _seed_eligible_drill(
    client: InMemoryFirestoreClient | _OptimisticFirestoreClient,
    *,
    drill_run_id: str = "drill-target",
) -> AnalysisExecutionRepository:
    courses = CourseRepository(client)
    drills = DrillRepository(client)
    answers = AnswerRepository(client)
    courses.create(
        Course(
            id="course-1",
            owner_user_id="owner-1",
            title="講座",
            markdown="# Before",
        )
    )
    drills.create(
        DrillRun(
            id=drill_run_id,
            course_id="course-1",
            status=DrillRunStatus.READY,
        )
    )
    for index in range(5):
        answers.create_submission(
            AnswerSubmission(
                id=f"answer-{index}",
                drill_run_id=drill_run_id,
                learner_name="受講者",
                status=AnswerStatus.GRADED,
                answers={"q1": "回答"},
                total_score=0,
                max_score=4,
            )
        )
    return AnalysisExecutionRepository(client)


def _run_together(*callbacks: Callable[[], T]) -> list[T]:
    ready = Barrier(len(callbacks) + 1)

    def after_barrier(callback: Callable[[], T]) -> T:
        ready.wait(timeout=2)
        return callback()

    with ThreadPoolExecutor(max_workers=len(callbacks)) as executor:
        futures = [executor.submit(after_barrier, callback) for callback in callbacks]
        ready.wait(timeout=2)
        return [future.result(timeout=2) for future in futures]


def _assert_answers_preserved(
    client: InMemoryFirestoreClient | _OptimisticFirestoreClient,
) -> None:
    answers = AnswerRepository(client).list_by_drill_run("drill-target")
    assert len(answers) == 5
    assert {answer.id for answer in answers} == {f"answer-{index}" for index in range(5)}
    assert all(answer.status is AnswerStatus.GRADED for answer in answers)


def _assert_single_start_state(
    client: InMemoryFirestoreClient,
    *,
    origin: AnalysisOrigin,
) -> None:
    courses = CourseRepository(client).list_all()
    drills = DrillRepository(client).list_by_course("course-1")
    patches = PatchRepository(client).list_by_course("course-1")
    assert len(courses) == 1
    assert courses[0].id == "course-1"
    assert courses[0].owner_user_id == "owner-1"
    assert courses[0].markdown == "# Before"
    assert courses[0].version == 1
    assert courses[0].latest_drill_run_id == "drill-target"
    assert courses[0].latest_drill_status is DrillRunStatus.ANALYZING
    assert courses[0].answer_count == 5
    assert courses[0].latest_patch_id is None
    assert courses[0].latest_patch_status is None
    assert len(drills) == 1
    assert drills[0].id == "drill-target"
    assert drills[0].status is DrillRunStatus.ANALYZING
    assert drills[0].analysis_origin is origin
    assert drills[0].latest_patch_id is None
    assert patches == []
    _assert_answers_preserved(client)


def test_concurrent_auto_triggers_start_analysis_at_most_once() -> None:
    client = InMemoryFirestoreClient()
    repository = _seed_eligible_drill(client)
    analysis_executor = _BlockingAnalysisExecutor()
    trigger = AutoAnalysisTrigger(repository, cast(AnalysisService, analysis_executor))
    ready = Barrier(3)

    def run_trigger() -> None:
        ready.wait(timeout=2)
        trigger.maybe_run("drill-target")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_trigger) for _ in range(2)]
        ready.wait(timeout=2)
        try:
            assert analysis_executor.entered.wait(timeout=2)
        finally:
            analysis_executor.release.set()
        for future in futures:
            future.result(timeout=2)

    assert len(analysis_executor.claims) == 1
    _assert_single_start_state(client, origin=AnalysisOrigin.AUTOMATIC)


def test_concurrent_manual_and_auto_claims_persist_exactly_one_start() -> None:
    client = InMemoryFirestoreClient()
    repository = _seed_eligible_drill(client)

    def manual_claim() -> AnalysisClaim | AppError:
        try:
            return repository.claim_manual_analysis("drill-target", "owner-1")
        except AppError as exc:
            return exc

    results = _run_together(
        lambda: repository.claim_auto_analysis("drill-target"),
        manual_claim,
    )
    automatic_result = results[0]
    manual_result = results[1]
    claims = [
        result for result in (automatic_result, manual_result) if isinstance(result, AnalysisClaim)
    ]

    assert len(claims) == 1
    if isinstance(automatic_result, AnalysisClaim):
        assert isinstance(manual_result, AppError)
        assert manual_result.code == "drill_not_analyzable"
    else:
        assert automatic_result is None
        assert isinstance(manual_result, AnalysisClaim)
    _assert_single_start_state(client, origin=claims[0].origin)


def _seed_patch_completion_race(
    client: _OptimisticFirestoreClient,
) -> tuple[AnalysisExecutionRepository, AnalysisClaim, DocumentPatch]:
    repository = _seed_eligible_drill(client)
    DrillRepository(client).create(
        DrillRun(
            id="drill-completing",
            course_id="course-1",
            status=DrillRunStatus.ANALYZING,
            analysis_origin=AnalysisOrigin.AUTOMATIC,
        )
    )
    claim = AnalysisClaim(
        course_id="course-1",
        drill_run_id="drill-completing",
        owner_user_id="owner-1",
        course_version=1,
        answer_ids=(),
        snapshot_agent_answer_count=0,
        snapshot_scored_answer_count=0,
        origin=AnalysisOrigin.AUTOMATIC,
    )
    patch = DocumentPatch(
        id="patch-race",
        course_id="course-1",
        drill_run_id="drill-completing",
        status=PatchStatus.PROPOSED,
        base_markdown="# Before",
        patched_markdown="# After",
        patch_summary="教材を改善",
        diff_text="--- before\n+++ after",
    )
    return repository, claim, patch


def _completed_timeline() -> list[AnalysisTimelineItem]:
    return [
        AnalysisTimelineItem(
            id="create_patch",
            title="修正案を作成",
            status=AnalysisStepStatus.COMPLETED,
        )
    ]


def _assert_patch_race_state(
    client: _OptimisticFirestoreClient,
    *,
    target_status: DrillRunStatus,
    target_origin: AnalysisOrigin | None,
    answer_count: int,
) -> None:
    courses = CourseRepository(client).list_all()
    drills = {drill.id: drill for drill in DrillRepository(client).list_by_course("course-1")}
    patches = PatchRepository(client).list_by_course("course-1")
    assert len(courses) == 1
    assert courses[0].id == "course-1"
    assert courses[0].owner_user_id == "owner-1"
    assert courses[0].markdown == "# Before"
    assert courses[0].version == 1
    assert courses[0].latest_drill_run_id == "drill-completing"
    assert courses[0].latest_drill_status is DrillRunStatus.ANALYZED
    assert courses[0].answer_count == answer_count
    assert courses[0].latest_patch_id == "patch-race"
    assert courses[0].latest_patch_status is PatchStatus.PROPOSED
    assert len(drills) == 2
    assert set(drills) == {"drill-target", "drill-completing"}
    assert drills["drill-target"].status is target_status
    assert drills["drill-target"].analysis_origin is target_origin
    assert drills["drill-target"].latest_patch_id is None
    assert drills["drill-completing"].status is DrillRunStatus.ANALYZED
    assert drills["drill-completing"].analysis_origin is AnalysisOrigin.AUTOMATIC
    assert drills["drill-completing"].latest_patch_id == "patch-race"
    assert len(patches) == 1
    assert patches[0].id == "patch-race"
    assert patches[0].status is PatchStatus.PROPOSED
    assert patches[0].analysis_origin is AnalysisOrigin.AUTOMATIC
    _assert_answers_preserved(client)


def test_patch_completion_winning_forces_auto_claim_retry_to_no_op() -> None:
    client = _OptimisticFirestoreClient()
    repository, completing_claim, patch = _seed_patch_completion_race(client)
    gate = _CommitGate(Event(), Event())

    def delayed_auto_claim() -> AnalysisClaim | None:
        client.gate_next_transaction(gate)
        return repository.claim_auto_analysis("drill-target")

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(delayed_auto_claim)
        try:
            assert gate.first_attempt_ready.wait(timeout=2)
            repository.complete_analysis(completing_claim, _completed_timeline(), patch)
        finally:
            gate.release_first_attempt.set()
        automatic_claim = future.result(timeout=2)

    assert gate.attempts == 2
    assert gate.retry_conflicts == [{(CourseRepository.collection, "course-1")}]
    assert automatic_claim is None
    _assert_patch_race_state(
        client,
        target_status=DrillRunStatus.READY,
        target_origin=AnalysisOrigin.MANUAL,
        answer_count=0,
    )


def test_auto_claim_winning_remains_started_when_patch_completion_retries() -> None:
    client = _OptimisticFirestoreClient()
    repository, completing_claim, patch = _seed_patch_completion_race(client)
    gate = _CommitGate(Event(), Event())

    def delayed_completion() -> DocumentPatch | None:
        client.gate_next_transaction(gate)
        return repository.complete_analysis(completing_claim, _completed_timeline(), patch)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(delayed_completion)
        try:
            assert gate.first_attempt_ready.wait(timeout=2)
            automatic_claim = repository.claim_auto_analysis("drill-target")
        finally:
            gate.release_first_attempt.set()
        completed_patch = future.result(timeout=2)

    assert gate.attempts == 2
    assert gate.retry_conflicts == [{(CourseRepository.collection, "course-1")}]
    assert automatic_claim is not None
    assert completed_patch is not None and completed_patch.id == "patch-race"
    _assert_patch_race_state(
        client,
        target_status=DrillRunStatus.ANALYZING,
        target_origin=AnalysisOrigin.AUTOMATIC,
        answer_count=5,
    )
