import pytest
from pydantic import ValidationError

from app.schemas import (
    AdminDrillQuestionResponse,
    AnalysisClaim,
    AnalysisOrigin,
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
    CourseSummary,
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


def test_drill_run_analyzed_answer_count_supports_legacy_and_camel_case_data() -> None:
    legacy_run = DrillRun.model_validate(
        {"id": "drill-1", "courseId": "course-1", "status": "ready"}
    )
    analyzed_run = DrillRun.model_validate(
        {
            "id": "drill-2",
            "courseId": "course-1",
            "status": "analyzed",
            "analyzedAnswerCount": 3,
        }
    )

    assert legacy_run.analyzed_answer_count is None
    assert legacy_run.model_dump(by_alias=True)["analyzedAnswerCount"] is None
    assert analyzed_run.analyzed_answer_count == 3
    assert analyzed_run.model_dump(by_alias=True)["analyzedAnswerCount"] == 3


def test_auto_analysis_data_contract_defaults_legacy_origin_and_serializes_camel_case() -> None:
    legacy_run = DrillRun.model_validate(
        {"id": "drill-legacy", "courseId": "course-1", "status": "analyzed"}
    )
    legacy_run_payload = legacy_run.model_dump(by_alias=True)
    legacy_patch = DocumentPatch.model_validate(
        {
            "id": "patch-legacy",
            "courseId": "course-1",
            "drillRunId": "drill-legacy",
            "status": "proposed",
            "baseMarkdown": "# Before",
            "patchedMarkdown": "# After",
            "patchSummary": "説明を追加",
            "diffText": "--- before",
        }
    )
    legacy_admin = DrillAdminResponse(
        id="drill-legacy",
        course_id="course-1",
        status=DrillRunStatus.ANALYZED,
        questions=[],
        rubric_summary=[],
        share_url=None,
        share_status=ShareStatus.UNAVAILABLE,
        answer_count=0,
        can_analyze=True,
    )

    assert legacy_run.analysis_origin is AnalysisOrigin.MANUAL
    assert legacy_run_payload["analysisOrigin"] == "manual"
    assert DrillRun.model_validate(legacy_run_payload) == legacy_run
    assert legacy_patch.analysis_origin is AnalysisOrigin.MANUAL
    assert legacy_patch.model_dump(by_alias=True)["analysisOrigin"] == "manual"
    assert DocumentPatch.model_validate(legacy_patch.model_dump(by_alias=True)) == legacy_patch
    legacy_admin_payload = legacy_admin.model_dump(by_alias=True)
    assert legacy_admin_payload["analysisOrigin"] == "manual"
    assert DrillAdminResponse.model_validate(legacy_admin_payload) == legacy_admin


def test_auto_analysis_data_contract_round_trips_dedicated_watermark_and_patch_id() -> None:
    current_run = DrillRun.model_validate(
        {
            "id": "drill-current",
            "courseId": "course-1",
            "status": "analyzed",
            "analyzedAnswerCount": 6,
            "autoAnalyzedScoredAnswerCount": 5,
            "analysisOrigin": "automatic",
            "latestPatchId": "patch-current",
        }
    )
    current_run_payload = current_run.model_dump(by_alias=True)

    assert current_run.analysis_origin is AnalysisOrigin.AUTOMATIC
    assert current_run.auto_analyzed_scored_answer_count == 5
    assert current_run.latest_patch_id == "patch-current"
    assert current_run_payload["analysisOrigin"] == "automatic"
    assert current_run_payload["autoAnalyzedScoredAnswerCount"] == 5
    assert current_run_payload["latestPatchId"] == "patch-current"
    assert DrillRun.model_validate(current_run_payload) == current_run


def test_auto_analysis_data_contract_round_trips_automatic_patch_origin() -> None:
    automatic_patch = DocumentPatch.model_validate(
        {
            "id": "patch-current",
            "courseId": "course-1",
            "drillRunId": "drill-current",
            "status": "proposed",
            "baseMarkdown": "# Before",
            "patchedMarkdown": "# After",
            "patchSummary": "説明を追加",
            "diffText": "--- before",
            "analysisOrigin": "automatic",
        }
    )
    automatic_patch_payload = automatic_patch.model_dump(by_alias=True)

    assert automatic_patch.analysis_origin is AnalysisOrigin.AUTOMATIC
    assert automatic_patch_payload["analysisOrigin"] == "automatic"
    assert DocumentPatch.model_validate(automatic_patch_payload) == automatic_patch


def test_auto_analysis_data_contract_defaults_drill_specific_patch_id_to_none() -> None:
    legacy_run = DrillRun.model_validate(
        {"id": "drill-legacy", "courseId": "course-1", "status": "analyzed"}
    )
    legacy_admin = DrillAdminResponse(
        id="drill-legacy",
        course_id="course-1",
        status=DrillRunStatus.ANALYZED,
        questions=[],
        rubric_summary=[],
        share_url=None,
        share_status=ShareStatus.UNAVAILABLE,
        answer_count=0,
        can_analyze=True,
    )

    assert legacy_run.latest_patch_id is None
    assert legacy_run.model_dump(by_alias=True)["latestPatchId"] is None
    assert legacy_admin.latest_patch_id is None
    assert legacy_admin.model_dump(by_alias=True)["latestPatchId"] is None


def test_auto_analysis_data_contract_rejects_negative_scored_watermark() -> None:
    with pytest.raises(ValidationError, match="autoAnalyzedScoredAnswerCount"):
        DrillRun.model_validate(
            {
                "id": "drill-1",
                "courseId": "course-1",
                "status": "analyzed",
                "autoAnalyzedScoredAnswerCount": -1,
            }
        )


def test_analysis_claim_keeps_agent_and_scored_snapshot_counts_separate() -> None:
    manual_claim = AnalysisClaim(
        course_id="course-1",
        drill_run_id="drill-1",
        owner_user_id="owner-1",
        course_version=3,
        answer_ids=("answer-1", "answer-2", "answer-unscored"),
        snapshot_agent_answer_count=3,
        snapshot_scored_answer_count=2,
        origin=AnalysisOrigin.MANUAL,
    )
    automatic_claim = AnalysisClaim.model_validate(
        {
            "courseId": "course-1",
            "drillRunId": "drill-1",
            "ownerUserId": "owner-1",
            "courseVersion": 3,
            "answerIds": ["answer-1", "answer-2"],
            "snapshotAgentAnswerCount": 2,
            "snapshotScoredAnswerCount": 2,
            "origin": "automatic",
        }
    )

    manual_payload = manual_claim.model_dump(by_alias=True)
    automatic_payload = automatic_claim.model_dump(by_alias=True)

    assert manual_claim.snapshot_agent_answer_count == 3
    assert manual_claim.snapshot_scored_answer_count == 2
    assert manual_payload["snapshotAgentAnswerCount"] == 3
    assert manual_payload["snapshotScoredAnswerCount"] == 2
    assert automatic_claim.origin is AnalysisOrigin.AUTOMATIC
    assert automatic_payload["snapshotAgentAnswerCount"] == 2
    assert automatic_payload["snapshotScoredAnswerCount"] == 2
    assert AnalysisClaim.model_validate(manual_payload) == manual_claim
    assert AnalysisClaim.model_validate(automatic_payload) == automatic_claim


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
    course_payload = CourseSummary(
        id="course-1",
        title="講座",
        version=1,
    ).model_dump(by_alias=True)

    assert course_payload["needsAnalysis"] is False
    assert admin_payload["needsAnalysis"] is False
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
