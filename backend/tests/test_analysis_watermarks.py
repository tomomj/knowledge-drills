from dataclasses import dataclass

import pytest

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.errors import AppError
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
    AnalysisStepStatus,
    AnswerStatus,
    AnswerSubmission,
    Course,
    DrillRun,
    DrillRunStatus,
)
from app.services.analysis_service import AnalysisService


class ScenarioAnalysisAgent:
    def __init__(self) -> None:
        self.outcome = "no_signal"

    def __call__(self, task_name: str, payload: dict[str, object]) -> dict[str, object]:
        if task_name == "analyze_failures":
            if self.outcome == "failure":
                raise RuntimeError("analysis agent unavailable")
            if self.outcome == "no_signal":
                return {"failureSignals": []}
            answers = payload.get("answers")
            sample_size = len(answers) if isinstance(answers, list) else 0
            return {
                "failureSignals": [
                    {
                        "id": "signal-1",
                        "title": "教材の説明不足",
                        "severity": "medium",
                        "evidence": ["同じ誤答が継続"],
                        "likelyCause": "例が不足",
                        "suspectedDocumentGap": "具体例がない",
                        "targetSections": ["## 基礎"],
                        "recommendedChange": "例を追加する",
                        "affectedCount": sample_size,
                        "sampleSize": sample_size,
                    }
                ]
            }
        if task_name == "propose_document_patch":
            return {
                "patchedMarkdown": "# Course\n\n## 基礎\n\n具体例を追加。\n",
                "patchSummary": "具体例を追加",
                "riskNotes": [],
            }
        raise AssertionError(f"unexpected task: {task_name}")


@dataclass(frozen=True)
class WatermarkWorkflow:
    service: AnalysisService
    execution_repository: AnalysisExecutionRepository
    course_repository: CourseRepository
    drill_repository: DrillRepository
    answer_repository: AnswerRepository
    patch_repository: PatchRepository
    agent: ScenarioAnalysisAgent


def _workflow(
    *,
    analyzed_answer_count: int | None = None,
    auto_analyzed_scored_answer_count: int | None = None,
) -> WatermarkWorkflow:
    client = InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    patch_repository = PatchRepository(client)
    execution_repository = AnalysisExecutionRepository(client)
    agent = ScenarioAnalysisAgent()
    course_repository.create(
        Course(
            id="course-1",
            owner_user_id="owner-1",
            title="Watermark course",
            markdown="# Course\n\n## 基礎\n",
            version=2,
        )
    )
    drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            course_version=2,
            status=DrillRunStatus.READY,
            analyzed_answer_count=analyzed_answer_count,
            auto_analyzed_scored_answer_count=auto_analyzed_scored_answer_count,
        )
    )
    service = AnalysisService(
        drill_repository,
        answer_repository,
        course_repository=course_repository,
        patch_repository=patch_repository,
        agent_client=AgentRuntimeClient(invoker=agent),
        execution_repository=execution_repository,
    )
    return WatermarkWorkflow(
        service=service,
        execution_repository=execution_repository,
        course_repository=course_repository,
        drill_repository=drill_repository,
        answer_repository=answer_repository,
        patch_repository=patch_repository,
        agent=agent,
    )


def _add_scored_answers(
    workflow: WatermarkWorkflow,
    prefix: str,
    count: int,
) -> None:
    for index in range(count):
        answer_id = f"{prefix}-scored-{index}"
        workflow.answer_repository.create_submission(
            AnswerSubmission(
                id=answer_id,
                drill_run_id="drill-1",
                learner_name=answer_id,
                status=AnswerStatus.GRADED,
                answers={"q1": "根拠が不足した回答"},
                total_score=0,
                max_score=4,
            )
        )


def _add_missing_score_answers(
    workflow: WatermarkWorkflow,
    prefix: str,
    count: int,
) -> None:
    for index in range(count):
        answer_id = f"{prefix}-missing-{index}"
        workflow.answer_repository.create_submission(
            AnswerSubmission(
                id=answer_id,
                drill_run_id="drill-1",
                learner_name=answer_id,
                status=AnswerStatus.GRADED,
                answers={"q1": "score fieldなし"},
            )
        )


def _assert_terminal_timeline(drill_run: DrillRun, *, patch_created: bool) -> None:
    statuses = {item.id: item.status for item in drill_run.analysis_timeline}
    assert statuses == {
        "collect_answers": AnalysisStepStatus.COMPLETED,
        "detect_failure_patterns": AnalysisStepStatus.COMPLETED,
        "match_course_evidence": AnalysisStepStatus.COMPLETED,
        "decide_patch_strategy": AnalysisStepStatus.COMPLETED,
        "create_patch": (
            AnalysisStepStatus.COMPLETED if patch_created else AnalysisStepStatus.SKIPPED
        ),
    }


def test_manual_then_automatic_success_advances_each_origin_snapshot_without_cross_counting() -> (
    None
):
    workflow = _workflow()
    _add_scored_answers(workflow, "initial", 4)
    _add_missing_score_answers(workflow, "initial", 10)
    before_manual = workflow.drill_repository.get("drill-1")
    assert before_manual is not None
    assert before_manual.analyzed_answer_count is None
    assert before_manual.auto_analyzed_scored_answer_count is None

    manual_patch = workflow.service.run_analysis("drill-1", "owner-1")

    after_manual = workflow.drill_repository.get("drill-1")
    assert manual_patch is None
    assert after_manual is not None
    assert after_manual.status is DrillRunStatus.ANALYZED
    assert after_manual.analysis_origin is AnalysisOrigin.MANUAL
    assert after_manual.analyzed_answer_count == 14
    assert after_manual.auto_analyzed_scored_answer_count == 4
    assert after_manual.latest_patch_id is None
    _assert_terminal_timeline(after_manual, patch_created=False)

    _add_scored_answers(workflow, "new", 5)
    automatic_claim = workflow.execution_repository.claim_auto_analysis("drill-1")

    assert automatic_claim is not None
    assert automatic_claim.origin is AnalysisOrigin.AUTOMATIC
    assert automatic_claim.answer_ids == (
        *(f"initial-scored-{index}" for index in range(4)),
        *(f"new-scored-{index}" for index in range(5)),
    )
    assert automatic_claim.snapshot_agent_answer_count == 9
    assert automatic_claim.snapshot_scored_answer_count == 9
    workflow.agent.outcome = "with_signal"
    automatic_patch = workflow.service.run_claimed_analysis(automatic_claim)

    after_automatic = workflow.drill_repository.get("drill-1")
    assert automatic_patch is not None
    assert after_automatic is not None
    assert after_automatic.status is DrillRunStatus.ANALYZED
    assert after_automatic.analysis_origin is AnalysisOrigin.AUTOMATIC
    assert after_automatic.analyzed_answer_count == 14
    assert after_automatic.auto_analyzed_scored_answer_count == 9
    assert after_automatic.latest_patch_id == automatic_patch.id
    assert automatic_patch.analysis_origin is AnalysisOrigin.AUTOMATIC
    assert workflow.patch_repository.get(automatic_patch.id) == automatic_patch
    _assert_terminal_timeline(after_automatic, patch_created=True)


def test_automatic_then_manual_no_signal_success_keeps_scored_watermark_monotonic() -> None:
    workflow = _workflow()
    _add_scored_answers(workflow, "automatic", 5)
    before_automatic = workflow.drill_repository.get("drill-1")
    assert before_automatic is not None
    assert before_automatic.analyzed_answer_count is None
    assert before_automatic.auto_analyzed_scored_answer_count is None
    automatic_claim = workflow.execution_repository.claim_auto_analysis("drill-1")
    assert automatic_claim is not None

    assert workflow.service.run_claimed_analysis(automatic_claim) is None

    after_automatic = workflow.drill_repository.get("drill-1")
    assert after_automatic is not None
    assert after_automatic.analysis_origin is AnalysisOrigin.AUTOMATIC
    assert after_automatic.analyzed_answer_count == 5
    assert after_automatic.auto_analyzed_scored_answer_count == 5
    _assert_terminal_timeline(after_automatic, patch_created=False)

    _add_missing_score_answers(workflow, "manual", 2)
    assert workflow.service.run_analysis("drill-1", "owner-1") is None

    after_manual = workflow.drill_repository.get("drill-1")
    assert after_manual is not None
    assert after_manual.status is DrillRunStatus.ANALYZED
    assert after_manual.analysis_origin is AnalysisOrigin.MANUAL
    assert after_manual.analyzed_answer_count == 7
    assert after_manual.auto_analyzed_scored_answer_count == 5
    assert after_manual.latest_patch_id is None
    _assert_terminal_timeline(after_manual, patch_created=False)
    assert workflow.execution_repository.claim_auto_analysis("drill-1") is None


@pytest.mark.parametrize("origin", [AnalysisOrigin.AUTOMATIC, AnalysisOrigin.MANUAL])
def test_agent_failure_preserves_both_watermarks_for_each_origin(origin: AnalysisOrigin) -> None:
    workflow = _workflow(
        analyzed_answer_count=3,
        auto_analyzed_scored_answer_count=2,
    )
    _add_scored_answers(workflow, "failure", 7)
    before_failure = workflow.drill_repository.get("drill-1")
    assert before_failure is not None
    assert before_failure.analyzed_answer_count == 3
    assert before_failure.auto_analyzed_scored_answer_count == 2
    claim = (
        workflow.execution_repository.claim_auto_analysis("drill-1")
        if origin is AnalysisOrigin.AUTOMATIC
        else workflow.execution_repository.claim_manual_analysis("drill-1", "owner-1")
    )
    assert claim is not None
    workflow.agent.outcome = "failure"

    with pytest.raises(RuntimeError, match="analysis agent unavailable"):
        workflow.service.run_claimed_analysis(claim)

    failed = workflow.drill_repository.get("drill-1")
    assert failed is not None
    assert failed.status is DrillRunStatus.READY
    assert failed.analysis_origin is origin
    assert failed.error_message == "analysis failed"
    assert failed.analyzed_answer_count == 3
    assert failed.auto_analyzed_scored_answer_count == 2
    assert failed.latest_patch_id is None
    assert [
        item.id for item in failed.analysis_timeline if item.status is AnalysisStepStatus.FAILED
    ] == ["detect_failure_patterns"]


@pytest.mark.parametrize("origin", [AnalysisOrigin.AUTOMATIC, AnalysisOrigin.MANUAL])
def test_course_version_mismatch_preserves_both_watermarks_for_each_origin(
    origin: AnalysisOrigin,
) -> None:
    workflow = _workflow(
        analyzed_answer_count=3,
        auto_analyzed_scored_answer_count=2,
    )
    _add_scored_answers(workflow, "stale", 7)
    before_stale = workflow.drill_repository.get("drill-1")
    assert before_stale is not None
    assert before_stale.analyzed_answer_count == 3
    assert before_stale.auto_analyzed_scored_answer_count == 2
    claim = (
        workflow.execution_repository.claim_auto_analysis("drill-1")
        if origin is AnalysisOrigin.AUTOMATIC
        else workflow.execution_repository.claim_manual_analysis("drill-1", "owner-1")
    )
    assert claim is not None
    course = workflow.course_repository.get("course-1")
    assert course is not None
    workflow.course_repository.update(course.model_copy(update={"version": 3}))

    with pytest.raises(AppError) as exc_info:
        workflow.service.run_claimed_analysis(claim)

    stale = workflow.drill_repository.get("drill-1")
    assert exc_info.value.code == "analysis_course_version_changed"
    assert stale is not None
    assert stale.status is DrillRunStatus.READY
    assert stale.analysis_origin is origin
    assert stale.error_message == "Course version changed during analysis."
    assert stale.analyzed_answer_count == 3
    assert stale.auto_analyzed_scored_answer_count == 2
    assert stale.latest_patch_id is None
    assert [
        item.id for item in stale.analysis_timeline if item.status is AnalysisStepStatus.FAILED
    ] == ["create_patch"]
