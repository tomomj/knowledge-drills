from typing import cast

import pytest

from app.clients.agent_runtime_client import AgentInvocationError, AgentRuntimeClient
from app.errors import AppError
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import (
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
)
from app.schemas import AnswerStatus, Course, DrillRun, DrillRunStatus
from app.services.analysis_service import AnalysisService


def _service() -> tuple[AnalysisService, DrillRepository, AnswerRepository]:
    client = InMemoryFirestoreClient()
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    return AnalysisService(drill_repository, answer_repository), drill_repository, answer_repository


def _proposal_service(
    invocations: list[tuple[str, dict[str, object]]],
) -> tuple[AnalysisService, DrillRepository, AnswerRepository, CourseRepository, PatchRepository]:
    client = InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    patch_repository = PatchRepository(client)
    course_repository.create(
        Course(id="course-1", owner_user_id="owner-1", title="講座", markdown="# Before\n")
    )

    def invoke(task_name: str, payload: dict[str, object]) -> dict[str, object]:
        invocations.append((task_name, payload))
        if task_name == "analyze_failures":
            return {
                "failureSignals": [
                    {
                        "id": "fs_test_001",
                        "title": "判断根拠の不足",
                        "severity": "medium",
                        "evidence": ["graded answer only"],
                        "likelyCause": "説明が薄い",
                        "suspectedDocumentGap": "例が不足",
                        "targetSections": ["## 方針"],
                        "recommendedChange": "例を追記",
                        "sampleSize": 1,
                        "confidenceNote": "少数回答に基づく傾向",
                    }
                ]
            }
        return {
            "patchedMarkdown": "# After\n",
            "patchSummary": "説明を追加",
            "riskNotes": ["要確認"],
        }

    return (
        AnalysisService(
            drill_repository,
            answer_repository,
            course_repository=course_repository,
            patch_repository=patch_repository,
            agent_client=AgentRuntimeClient(invoker=invoke),
        ),
        drill_repository,
        answer_repository,
        course_repository,
        patch_repository,
    )


def test_start_analysis_sets_drill_to_analyzing_when_graded_answer_exists() -> None:
    service, drill_repository, answer_repository = _service()
    drill_repository.create(
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.READY)
    )
    answer_repository.create(
        id="answer-1",
        drill_run_id="drill-1",
        learner_name="受講者",
        status=AnswerStatus.GRADED,
        answers={"q1": "回答"},
    )

    drill_run = service.start_analysis("drill-1")
    saved = drill_repository.get("drill-1")

    assert drill_run.status == "analyzing"
    assert saved is not None
    assert saved.status == "analyzing"


def test_start_analysis_requires_at_least_one_graded_answer() -> None:
    service, drill_repository, _answer_repository = _service()
    drill_repository.create(
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.READY)
    )

    with pytest.raises(AppError) as exc_info:
        service.start_analysis("drill-1")

    assert exc_info.value.code == "no_graded_answers"


def test_start_analysis_rejects_generation_failed_drill_but_allows_analysis_retry() -> None:
    service, drill_repository, answer_repository = _service()
    drill_repository.create(
        DrillRun(
            id="generation-failed",
            course_id="course-1",
            status=DrillRunStatus.FAILED,
            error_message="drill generation failed",
        )
    )
    drill_repository.create(
        DrillRun(
            id="analysis-failed",
            course_id="course-1",
            status=DrillRunStatus.FAILED,
            error_message="analysis failed",
        )
    )
    answer_repository.create(
        id="answer-1",
        drill_run_id="analysis-failed",
        learner_name="受講者",
        status=AnswerStatus.GRADED,
        answers={"q1": "回答"},
    )

    with pytest.raises(AppError) as exc_info:
        service.start_analysis("generation-failed")
    retry = service.start_analysis("analysis-failed")

    assert exc_info.value.code == "drill_not_analyzable"
    assert retry.status == "analyzing"


def test_generate_patch_proposal_uses_only_graded_answers_and_builds_diff() -> None:
    invocations: list[tuple[str, dict[str, object]]] = []
    (
        service,
        drill_repository,
        answer_repository,
        _course_repository,
        _patch_repository,
    ) = _proposal_service(invocations)
    drill_repository.create(
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.ANALYZING)
    )
    answer_repository.create(
        id="graded-answer",
        drill_run_id="drill-1",
        learner_name="受講者1",
        status=AnswerStatus.GRADED,
        answers={"q1": "回答"},
    )
    answer_repository.create(
        id="failed-answer",
        drill_run_id="drill-1",
        learner_name="受講者2",
        status=AnswerStatus.FAILED,
        answers={"q1": "失敗"},
    )

    patch = service.generate_patch_proposal("drill-1")

    analysis_payload = invocations[0][1]
    answers = cast(list[object], analysis_payload["answers"])
    grading_results = cast(list[object], analysis_payload["gradingResults"])
    assert invocations[0][0] == "analyze_failures"
    assert invocations[1][0] == "propose_document_patch"
    assert analysis_payload["courseMarkdown"] == "# Before\n"
    assert len(cast(list[object], analysis_payload["questions"])) == 0
    assert len(answers) == 1
    assert len(grading_results) == 0
    assert patch.patched_markdown == "# After\n"
    assert patch.risk_notes == ["要確認"]
    assert "-# Before" in patch.diff_text
    assert "+# After" in patch.diff_text


def test_run_analysis_persists_patch_and_latest_state() -> None:
    invocations: list[tuple[str, dict[str, object]]] = []
    service, drill_repository, answer_repository, course_repository, patch_repository = (
        _proposal_service(invocations)
    )
    drill_repository.create(
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.READY)
    )
    answer_repository.create(
        id="graded-answer",
        drill_run_id="drill-1",
        learner_name="受講者1",
        status=AnswerStatus.GRADED,
        answers={"q1": "回答"},
    )

    patch = service.run_analysis("drill-1", "owner-1")

    saved_patch = patch_repository.get(patch.id)
    saved_drill = drill_repository.get("drill-1")
    saved_course = course_repository.get("course-1")
    assert saved_patch is not None
    assert saved_drill is not None
    assert saved_course is not None
    assert saved_patch.status == "proposed"
    assert saved_drill.status == "analyzed"
    assert saved_course.latest_patch_id == patch.id
    assert saved_course.latest_drill_run_id == "drill-1"


def test_run_analysis_marks_drill_failed_when_generation_fails() -> None:
    client = InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    patch_repository = PatchRepository(client)
    course_repository.create(
        Course(id="course-1", owner_user_id="owner-1", title="講座", markdown="# Before\n")
    )
    drill_repository.create(
        DrillRun(id="drill-1", course_id="course-1", status=DrillRunStatus.READY)
    )
    answer_repository.create(
        id="graded-answer",
        drill_run_id="drill-1",
        learner_name="受講者1",
        status=AnswerStatus.GRADED,
        answers={"q1": "回答"},
    )
    service = AnalysisService(
        drill_repository,
        answer_repository,
        course_repository=course_repository,
        patch_repository=patch_repository,
        agent_client=AgentRuntimeClient(
            invoker=lambda _task_name, _payload: {"invalid": "payload"}
        ),
    )

    with pytest.raises(AgentInvocationError):
        service.run_analysis("drill-1", "owner-1")

    saved_drill = drill_repository.get("drill-1")
    assert saved_drill is not None
    assert saved_drill.status == "failed"
    assert saved_drill.error_message == "analysis failed"
