import pytest
from pydantic import ValidationError

from app.schemas import (
    AdminDrillQuestionResponse,
    AnalysisReviewNote,
    AnalysisReviewSource,
    AnalysisReviewTimelineStep,
    AnalysisStepStatus,
    AnalysisTimelineItem,
    AnswerStatus,
    AnswerSubmission,
    Course,
    CourseCreateRequest,
    CourseMetricsResponse,
    CourseMetricsRun,
    CourseRevision,
    CourseUpdateRequest,
    DocumentPatch,
    DrillAdminResponse,
    DrillGenerationRequest,
    DrillGenerationResponse,
    DrillQuestion,
    DrillRun,
    DrillRunStatus,
    DrillScoreSummary,
    FailureAnalysisResponse,
    FailureSeverity,
    FailureSignal,
    LearnerDrillQuestionResponse,
    PatchStatus,
    QuestionScoreSummary,
    RubricItem,
    ShareStatus,
    SourceEvidence,
)


def _question() -> DrillQuestion:
    return DrillQuestion(
        id="q1",
        question="顧客対応でどの判断をするか説明してください。",
        intent="実務判断を確認する",
        rubric=[RubricItem(criterion="根拠を示す", points=4)],
        ideal_answer="講座の根拠に基づき判断する。",
        source_evidence=[SourceEvidence(section_heading="対応方針", excerpt="## 対応方針")],
        max_score=4,
    )


def test_status_unions_accept_expected_values() -> None:
    assert DrillRunStatus("generating") == "generating"
    assert AnswerStatus("graded") == "graded"
    assert PatchStatus("stale") == "stale"

    with pytest.raises(ValueError):
        DrillRunStatus("done")


def test_learner_question_response_excludes_rubric_and_ideal_answer() -> None:
    question = _question()

    admin_payload = AdminDrillQuestionResponse.from_domain(question).model_dump(by_alias=True)
    learner_payload = LearnerDrillQuestionResponse.from_domain(question).model_dump(by_alias=True)

    assert "rubric" in admin_payload
    assert "idealAnswer" in admin_payload
    assert admin_payload["question"] == "顧客対応でどの判断をするか説明してください。"
    assert "rubric" not in learner_payload
    assert "idealAnswer" not in learner_payload
    assert learner_payload["question"] == "顧客対応でどの判断をするか説明してください。"
    assert learner_payload["maxScore"] == 4


def test_agent_drill_generation_requires_three_questions() -> None:
    with pytest.raises(ValidationError):
        DrillGenerationResponse(questions=[_question(), _question()])

    response = DrillGenerationResponse(
        questions=[
            _question(),
            _question().model_copy(update={"id": "q2"}),
            _question().model_copy(update={"id": "q3"}),
        ]
    )

    assert len(response.questions) == 3


def test_failure_signal_carries_sample_size_and_confidence_note() -> None:
    signal = FailureSignal(
        title="判断基準の混同",
        severity=FailureSeverity.MEDIUM,
        evidence=["q1 の不足点が複数回答に出た"],
        likely_cause="条件分岐の説明が不足している",
        suspected_document_gap="例外時の判断基準が薄い",
        target_sections=["## 対応方針"],
        recommended_change="例外条件を追記する",
        affected_count=1,
        sample_size=2,
        confidence_note="少数回答に基づく傾向",
    )
    response = FailureAnalysisResponse(failure_signals=[signal])

    payload = response.model_dump(by_alias=True)
    assert payload["failureSignals"][0]["id"].startswith("fs_")
    assert payload["failureSignals"][0]["affectedCount"] == 1
    assert payload["failureSignals"][0]["sampleSize"] == 2
    assert payload["failureSignals"][0]["likelyCause"] == "条件分岐の説明が不足している"
    assert payload["failureSignals"][0]["suspectedDocumentGap"] == "例外時の判断基準が薄い"
    assert payload["failureSignals"][0]["confidenceNote"] == "少数回答に基づく傾向"


def test_failure_signal_rejects_affected_count_over_sample_size() -> None:
    with pytest.raises(ValidationError):
        FailureSignal(
            title="判断基準の混同",
            severity=FailureSeverity.MEDIUM,
            evidence=["q1 の不足点が複数回答に出た"],
            likely_cause="条件分岐の説明が不足している",
            suspected_document_gap="例外時の判断基準が薄い",
            target_sections=["## 対応方針"],
            recommended_change="例外条件を追記する",
            affected_count=3,
            sample_size=2,
        )


def test_document_patch_and_answer_submission_domain_models() -> None:
    answer = AnswerSubmission(
        id="a1",
        drill_run_id="drill-1",
        learner_name="受講者",
        status=AnswerStatus.GRADING,
        answers={"q1": "回答"},
    )
    patch = DocumentPatch(
        id="patch-1",
        course_id="course-1",
        drill_run_id="drill-1",
        status=PatchStatus.PROPOSED,
        base_markdown="# Before",
        patched_markdown="# After",
        patch_summary="説明を追加",
        risk_notes=["要確認"],
        diff_text="--- before",
    )

    assert answer.status == "grading"
    assert patch.status == "proposed"


def test_hackathon_feedback_schema_defaults_support_existing_documents() -> None:
    course = Course.model_validate({"id": "course-1", "title": "講座", "markdown": "# Body"})
    revision = CourseRevision.model_validate(
        {"courseId": "course-1", "version": 1, "title": "講座", "markdown": "# Body"}
    )
    drill_run = DrillRun.model_validate(
        {"id": "drill-1", "courseId": "course-1", "status": "ready"}
    )
    patch = DocumentPatch(
        id="patch-1",
        course_id="course-1",
        drill_run_id="drill-1",
        status=PatchStatus.PROPOSED,
        base_markdown="# Before",
        patched_markdown="# After",
        patch_summary="説明を追加",
        diff_text="--- before",
    )
    analysis = FailureAnalysisResponse(failure_signals=[])

    assert course.drill_focus is None
    assert revision.drill_focus is None
    assert drill_run.drill_focus is None
    assert drill_run.analysis_timeline == []
    assert patch.analysis_timeline == []
    assert analysis.perspectives == []


def test_drill_focus_alias_and_length_constraints() -> None:
    create_payload = CourseCreateRequest.model_validate(
        {"title": "講座", "markdown": "# Body", "drillFocus": "重要な例外条件"}
    )
    update_payload = CourseUpdateRequest.model_validate(
        {"title": "講座", "markdown": "# Body", "drill_focus": "別の観点"}
    )
    generation_payload = DrillGenerationRequest.model_validate(
        {
            "courseTitle": "講座",
            "courseMarkdown": "# Body",
            "drillFocus": "顧客影響の説明",
        }
    )

    assert create_payload.drill_focus == "重要な例外条件"
    assert update_payload.drill_focus == "別の観点"
    assert generation_payload.drill_focus == "顧客影響の説明"
    assert create_payload.model_dump(by_alias=True)["drillFocus"] == "重要な例外条件"

    with pytest.raises(ValidationError):
        CourseCreateRequest(title="講座", markdown="# Body", drill_focus="あ" * 501)


def test_timeline_score_summary_and_metrics_use_camel_case_aliases() -> None:
    timeline_item = AnalysisTimelineItem(
        id="collect_answers",
        title="回答データを収集",
        status=AnalysisStepStatus.COMPLETED,
        summary="採点済み回答 2 件を収集しました",
        evidence=["平均点 3.0 / 4"],
        completed_at="2026-07-08T00:00:00Z",
    )
    score_summary = DrillScoreSummary(
        graded_answer_count=2,
        average_score=3.0,
        max_score=4,
        questions=[
            QuestionScoreSummary(
                question_id="q1",
                average_score=3.0,
                max_score=4,
                graded_answer_count=2,
                common_missing_points=["例外条件"],
                failure_tags=["判断基準"],
            )
        ],
    )
    admin = DrillAdminResponse(
        id="drill-1",
        course_id="course-1",
        course_version=1,
        status=DrillRunStatus.READY,
        questions=[],
        rubric_summary=[],
        share_url="/drills/token",
        share_status=ShareStatus.OPEN,
        answer_count=2,
        can_analyze=True,
        drill_focus="重要な例外条件",
        score_summary=score_summary,
        analysis_timeline=[timeline_item],
    )
    metrics = CourseMetricsResponse(
        course_id="course-1",
        runs=[
            CourseMetricsRun(
                drill_run_id="drill-1",
                course_version=1,
                answer_count=2,
                average_score=3.0,
                max_score=4,
            )
        ],
    )

    admin_payload = admin.model_dump(by_alias=True)
    metrics_payload = metrics.model_dump(by_alias=True)

    assert admin_payload["drillFocus"] == "重要な例外条件"
    assert admin_payload["scoreSummary"]["gradedAnswerCount"] == 2
    assert admin_payload["scoreSummary"]["questions"][0]["commonMissingPoints"] == ["例外条件"]
    assert admin_payload["analysisTimeline"][0]["completedAt"] == "2026-07-08T00:00:00Z"
    assert metrics_payload["runs"][0]["drillRunId"] == "drill-1"


def test_failure_analysis_response_accepts_optional_perspectives() -> None:
    response = FailureAnalysisResponse.model_validate(
        {
            "failureSignals": [],
            "perspectives": [
                {
                    "id": "material_gap",
                    "title": "教材ギャップ",
                    "summary": "例外条件の説明不足が見られます",
                }
            ],
        }
    )

    assert response.perspectives[0].summary == "例外条件の説明不足が見られます"


def test_failure_analysis_response_accepts_optional_review_notes() -> None:
    existing_response = FailureAnalysisResponse(failure_signals=[])
    response = FailureAnalysisResponse.model_validate(
        {
            "failureSignals": [],
            "reviewNotes": [
                {
                    "id": "review-note-1",
                    "source": "critic_reviewer",
                    "timelineStep": "decide_patch_strategy",
                    "title": "採用所見のレビュー",
                    "summary": "approvedFindingIds に含まれる所見だけを採用できます",
                    "evidence": ["approvedFindingIds: finding-1"],
                }
            ],
        }
    )

    assert existing_response.review_notes == []
    assert response.review_notes[0] == AnalysisReviewNote(
        id="review-note-1",
        source=AnalysisReviewSource.CRITIC_REVIEWER,
        timeline_step=AnalysisReviewTimelineStep.DECIDE_PATCH_STRATEGY,
        title="採用所見のレビュー",
        summary="approvedFindingIds に含まれる所見だけを採用できます",
        evidence=["approvedFindingIds: finding-1"],
    )
    assert response.model_dump(by_alias=True)["reviewNotes"][0]["timelineStep"] == (
        "decide_patch_strategy"
    )
