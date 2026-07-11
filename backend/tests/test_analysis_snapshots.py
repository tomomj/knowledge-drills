from dataclasses import dataclass
from typing import cast

import pytest

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import (
    AnalysisExecutionRepository,
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
)
from app.schemas import (
    AnalysisOrigin,
    AnswerStatus,
    AnswerSubmission,
    Course,
    DrillRun,
    DrillRunStatus,
)
from app.services.analysis_service import AnalysisService


class RecordingAnalysisAgent:
    def __init__(self) -> None:
        self.analysis_answer_ids: list[tuple[str, ...]] = []

    def __call__(self, task_name: str, payload: dict[str, object]) -> dict[str, object]:
        if task_name != "analyze_failures":
            raise AssertionError(f"unexpected task: {task_name}")
        answers = cast(list[dict[str, object]], payload["answers"])
        self.analysis_answer_ids.append(tuple(cast(str, answer["id"]) for answer in answers))
        return {"failureSignals": []}


@dataclass(frozen=True)
class AnalysisWorkflow:
    service: AnalysisService
    execution_repository: AnalysisExecutionRepository
    drill_repository: DrillRepository
    answer_repository: AnswerRepository
    agent: RecordingAnalysisAgent


def _workflow() -> AnalysisWorkflow:
    client = InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    execution_repository = AnalysisExecutionRepository(client)
    agent = RecordingAnalysisAgent()
    course_repository.create(
        Course(
            id="course-1",
            owner_user_id="owner-1",
            title="Snapshot course",
            markdown="# Course\n",
            version=2,
        )
    )
    drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            course_version=2,
            status=DrillRunStatus.READY,
        )
    )
    service = AnalysisService(
        drill_repository,
        answer_repository,
        course_repository=course_repository,
        patch_repository=PatchRepository(client),
        agent_client=AgentRuntimeClient(invoker=agent),
        execution_repository=execution_repository,
    )
    return AnalysisWorkflow(
        service=service,
        execution_repository=execution_repository,
        drill_repository=drill_repository,
        answer_repository=answer_repository,
        agent=agent,
    )


def _add_scored_answers(
    workflow: AnalysisWorkflow,
    answer_ids: tuple[str, ...],
) -> None:
    for answer_id in answer_ids:
        workflow.answer_repository.create_submission(
            AnswerSubmission(
                id=answer_id,
                drill_run_id="drill-1",
                learner_name=answer_id,
                status=AnswerStatus.GRADED,
                answers={"q1": "insufficient answer"},
                total_score=0,
                max_score=4,
            )
        )


def _add_missing_score_answer(workflow: AnalysisWorkflow, answer_id: str) -> None:
    workflow.answer_repository.create_submission(
        AnswerSubmission(
            id=answer_id,
            drill_run_id="drill-1",
            learner_name=answer_id,
            status=AnswerStatus.GRADED,
            answers={"q1": "answer without a score"},
        )
    )


def _seed_mixed_answers(workflow: AnalysisWorkflow) -> tuple[tuple[str, ...], str]:
    scored_ids = tuple(f"scored-{index}" for index in range(5))
    missing_score_id = "missing-score"
    _add_scored_answers(workflow, scored_ids)
    _add_missing_score_answer(workflow, missing_score_id)
    return scored_ids, missing_score_id


def test_manual_success_keeps_scored_watermark_separate_for_next_auto_claim() -> None:
    workflow = _workflow()
    initial_scored_ids = tuple(f"manual-scored-{index}" for index in range(4))
    _add_scored_answers(workflow, initial_scored_ids)
    _add_missing_score_answer(workflow, "manual-missing-score")

    workflow.service.run_analysis("drill-1", "owner-1")

    after_manual = workflow.drill_repository.get("drill-1")
    assert after_manual is not None
    assert workflow.agent.analysis_answer_ids == [(*initial_scored_ids, "manual-missing-score")]
    assert after_manual.analyzed_answer_count == 5
    assert after_manual.auto_analyzed_scored_answer_count == 4

    new_scored_ids = tuple(f"auto-new-{index}" for index in range(5))
    _add_scored_answers(workflow, new_scored_ids)

    auto_claim = workflow.execution_repository.claim_auto_analysis("drill-1")

    assert auto_claim is not None
    assert auto_claim.origin is AnalysisOrigin.AUTOMATIC
    assert auto_claim.answer_ids == (*initial_scored_ids, *new_scored_ids)
    assert auto_claim.snapshot_agent_answer_count == 9
    assert auto_claim.snapshot_scored_answer_count == 9


@pytest.mark.parametrize("origin", [AnalysisOrigin.AUTOMATIC, AnalysisOrigin.MANUAL])
def test_claimed_executor_ignores_scored_answer_added_after_origin_snapshot(
    origin: AnalysisOrigin,
) -> None:
    workflow = _workflow()
    scored_ids, missing_score_id = _seed_mixed_answers(workflow)
    claim = (
        workflow.execution_repository.claim_auto_analysis("drill-1")
        if origin is AnalysisOrigin.AUTOMATIC
        else workflow.execution_repository.claim_manual_analysis("drill-1", "owner-1")
    )
    assert claim is not None
    expected_ids = (
        scored_ids if origin is AnalysisOrigin.AUTOMATIC else (*scored_ids, missing_score_id)
    )
    expected_agent_count = 5 if origin is AnalysisOrigin.AUTOMATIC else 6
    assert claim.answer_ids == expected_ids
    assert claim.snapshot_agent_answer_count == expected_agent_count
    assert claim.snapshot_scored_answer_count == 5

    _add_scored_answers(workflow, (f"late-{origin.value}",))
    workflow.service.run_claimed_analysis(claim)

    saved = workflow.drill_repository.get("drill-1")
    assert workflow.agent.analysis_answer_ids == [expected_ids]
    assert saved is not None
    assert saved.analyzed_answer_count == expected_agent_count
    assert saved.auto_analyzed_scored_answer_count == 5
    assert len(workflow.answer_repository.list_by_drill_run("drill-1")) == 7


def test_same_mixed_answer_set_never_crosses_auto_and_manual_snapshot_counts() -> None:
    workflow = _workflow()
    scored_ids, missing_score_id = _seed_mixed_answers(workflow)

    auto_claim = workflow.execution_repository.claim_auto_analysis("drill-1")
    assert auto_claim is not None
    workflow.service.run_claimed_analysis(auto_claim)

    manual_claim = workflow.execution_repository.claim_manual_analysis("drill-1", "owner-1")
    workflow.service.run_claimed_analysis(manual_claim)

    assert auto_claim.answer_ids == scored_ids
    assert auto_claim.snapshot_agent_answer_count == 5
    assert auto_claim.snapshot_scored_answer_count == 5
    assert manual_claim.answer_ids == (*scored_ids, missing_score_id)
    assert manual_claim.snapshot_agent_answer_count == 6
    assert manual_claim.snapshot_scored_answer_count == 5
    assert workflow.agent.analysis_answer_ids == [
        scored_ids,
        (*scored_ids, missing_score_id),
    ]
    saved = workflow.drill_repository.get("drill-1")
    assert saved is not None
    assert saved.analysis_origin is AnalysisOrigin.MANUAL
    assert saved.analyzed_answer_count == 6
    assert saved.auto_analyzed_scored_answer_count == 5
