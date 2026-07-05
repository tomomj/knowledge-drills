import pytest
from pydantic import ValidationError

from app.schemas import (
    AdminDrillQuestionResponse,
    AnswerStatus,
    AnswerSubmission,
    DocumentPatch,
    DrillGenerationResponse,
    DrillQuestion,
    DrillRunStatus,
    FailureAnalysisResponse,
    FailureSeverity,
    FailureSignal,
    LearnerDrillQuestionResponse,
    PatchStatus,
    RubricItem,
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
        sample_size=2,
        confidence_note="少数回答に基づく傾向",
    )
    response = FailureAnalysisResponse(failure_signals=[signal])

    payload = response.model_dump(by_alias=True)
    assert payload["failureSignals"][0]["id"].startswith("fs_")
    assert payload["failureSignals"][0]["sampleSize"] == 2
    assert payload["failureSignals"][0]["likelyCause"] == "条件分岐の説明が不足している"
    assert payload["failureSignals"][0]["suspectedDocumentGap"] == "例外時の判断基準が薄い"
    assert payload["failureSignals"][0]["confidenceNote"] == "少数回答に基づく傾向"


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
