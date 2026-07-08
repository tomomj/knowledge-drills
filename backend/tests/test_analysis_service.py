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
from app.schemas import AnalysisStepStatus, AnswerStatus, Course, DrillRun, DrillRunStatus
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
                ],
                "perspectives": [
                    {
                        "id": "material_gap",
                        "title": "教材ギャップ",
                        "summary": "例が不足している",
                    },
                    {
                        "id": "question_quality",
                        "title": "設問品質",
                        "summary": "設問は根拠提示を求めている",
                    },
                    {
                        "id": "learner_pattern",
                        "title": "つまずきパターン",
                        "summary": "根拠への言及が抜けている",
                    },
                ],
                "reviewNotes": [
                    {
                        "id": "looks-like-decide-but-field-wins",
                        "source": "evidence_critic",
                        "timelineStep": "match_course_evidence",
                        "title": "根拠レビュー",
                        "summary": "教材根拠と採点根拠が一致",
                        "evidence": ["## 方針"],
                    },
                    {
                        "id": "looks-like-match-but-field-wins",
                        "source": "critic_reviewer",
                        "timelineStep": "decide_patch_strategy",
                        "title": "採用レビュー",
                        "summary": "finding-1 のみ採用",
                        "evidence": ["approvedFindingIds: finding-1"],
                    },
                    {
                        "id": "finalizer-note",
                        "source": "finalizer",
                        "timelineStep": "decide_patch_strategy",
                        "title": "最終化",
                        "summary": "未承認所見は採用しない",
                        "evidence": [],
                    },
                ],
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
    assert [item.id for item in saved.analysis_timeline] == [
        "collect_answers",
        "detect_failure_patterns",
        "match_course_evidence",
        "decide_patch_strategy",
        "create_patch",
    ]
    assert saved.analysis_timeline[0].status == AnalysisStepStatus.RUNNING
    assert [item.status for item in saved.analysis_timeline[1:]] == [
        AnalysisStepStatus.PENDING,
        AnalysisStepStatus.PENDING,
        AnalysisStepStatus.PENDING,
        AnalysisStepStatus.PENDING,
    ]


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
    assert [item.status for item in saved_patch.analysis_timeline] == [
        AnalysisStepStatus.COMPLETED,
        AnalysisStepStatus.COMPLETED,
        AnalysisStepStatus.COMPLETED,
        AnalysisStepStatus.COMPLETED,
        AnalysisStepStatus.COMPLETED,
    ]
    assert saved_drill.status == "analyzed"
    assert saved_course.latest_patch_id == patch.id
    assert saved_course.latest_patch_status == "proposed"
    assert saved_course.latest_drill_run_id == "drill-1"
    assert saved_course.latest_drill_status == "analyzed"
    assert [item.status for item in saved_drill.analysis_timeline] == [
        AnalysisStepStatus.COMPLETED,
        AnalysisStepStatus.COMPLETED,
        AnalysisStepStatus.COMPLETED,
        AnalysisStepStatus.COMPLETED,
        AnalysisStepStatus.COMPLETED,
    ]
    assert saved_drill.analysis_timeline[0].summary == "採点済み回答 1 件を収集しました"
    assert saved_drill.analysis_timeline[1].evidence == [
        "教材ギャップ: 例が不足している",
        "設問品質: 設問は根拠提示を求めている",
        "つまずきパターン: 根拠への言及が抜けている",
    ]
    assert saved_drill.analysis_timeline[2].evidence == [
        "根拠レビュー: 教材根拠と採点根拠が一致 (## 方針)",
        "## 方針",
    ]
    assert saved_drill.analysis_timeline[3].evidence == [
        "採用レビュー: finding-1 のみ採用 (approvedFindingIds: finding-1)",
        "最終化: 未承認所見は採用しない",
        "例を追記",
    ]
    assert saved_patch.analysis_timeline == saved_drill.analysis_timeline


def test_run_analysis_saves_intermediate_timeline_before_agent_calls() -> None:
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
    observed_statuses: list[dict[str, str]] = []

    def invoke(task_name: str, _payload: dict[str, object]) -> dict[str, object]:
        saved_drill = drill_repository.get("drill-1")
        assert saved_drill is not None
        observed_statuses.append(
            {item.id: item.status.value for item in saved_drill.analysis_timeline}
        )
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
                    }
                ]
            }
        return {
            "patchedMarkdown": "# After\n",
            "patchSummary": "説明を追加",
            "riskNotes": ["要確認"],
        }

    service = AnalysisService(
        drill_repository,
        answer_repository,
        course_repository=course_repository,
        patch_repository=patch_repository,
        agent_client=AgentRuntimeClient(invoker=invoke),
    )

    service.run_analysis("drill-1", "owner-1")

    saved_drill = drill_repository.get("drill-1")
    assert saved_drill is not None
    assert observed_statuses[0]["collect_answers"] == "completed"
    assert observed_statuses[0]["detect_failure_patterns"] == "running"
    assert observed_statuses[1]["detect_failure_patterns"] == "completed"
    assert observed_statuses[1]["match_course_evidence"] == "completed"
    assert observed_statuses[1]["decide_patch_strategy"] == "completed"
    assert observed_statuses[1]["create_patch"] == "running"
    assert saved_drill.analysis_timeline[1].evidence == ["判断根拠の不足"]


def test_run_analysis_marks_running_step_failed_and_restores_ready_when_analysis_fails() -> None:
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
    saved_course = course_repository.get("course-1")
    assert saved_drill is not None
    assert saved_course is not None
    assert saved_drill.status == "ready"
    assert saved_drill.error_message == "analysis failed"
    assert saved_course.latest_drill_run_id == "drill-1"
    assert saved_course.latest_drill_status == "ready"
    failed_steps = [
        item for item in saved_drill.analysis_timeline if item.status == AnalysisStepStatus.FAILED
    ]
    assert len(failed_steps) == 1
    assert failed_steps[0].id == "detect_failure_patterns"
    assert failed_steps[0].summary == "analysis failed"
