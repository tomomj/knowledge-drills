import pytest
from _pytest.logging import LogCaptureFixture

from app.clients.agent_runtime_client import AgentInvocationError, AgentRuntimeClient
from app.schemas import (
    AnswerStatus,
    AnswerSubmission,
    DocumentPatchRequest,
    DocumentPatchResponse,
    DrillGenerationRequest,
    DrillGenerationResponse,
    DrillQuestion,
    FailureAnalysisRequest,
    FailureAnalysisResponse,
    GradingRequest,
    GradingResponse,
)


def _question_payload(question_id: str = "q1") -> dict[str, object]:
    return {
        "id": question_id,
        "question": "顧客対応で判断理由を書いてください。",
        "intent": "判断理由を見る",
        "rubric": [{"criterion": "根拠", "points": 4, "required": True}],
        "idealAnswer": "根拠に基づき判断する。",
        "sourceEvidence": [{"sectionHeading": "方針", "excerpt": "## 方針"}],
        "maxScore": 4,
    }


def _grading_response_payload(question_id: str = "q1", score: int = 3) -> dict[str, object]:
    return {
        "questionId": question_id,
        "score": score,
        "maxScore": 4,
        "correctPoints": ["根拠を示している"],
        "missingPoints": ["例外条件を補える"],
        "feedback": "根拠は示せています。",
        "failureTags": ["missing_exception"],
    }


def _grading_request(question_id: str = "q1", max_score: int = 4) -> GradingRequest:
    question = _question_payload(question_id)
    question["maxScore"] = max_score
    return GradingRequest(question=DrillQuestion.model_validate(question), learner_answer="回答")


def _failure_signal_payload(sample_size: int = 2) -> dict[str, object]:
    return {
        "id": "fs_test_001",
        "title": "例外条件の不足",
        "severity": "medium",
        "evidence": ["q1 で例外条件が不足している"],
        "likelyCause": "資料の例外条件が見つけにくい",
        "suspectedDocumentGap": "判断基準に例外条件が不足",
        "targetSections": ["## 判断基準"],
        "recommendedChange": "例外条件を判断基準に追記する",
        "affectedCount": 1,
        "sampleSize": sample_size,
    }


def _failure_analysis_request(answer_count: int = 2) -> FailureAnalysisRequest:
    return FailureAnalysisRequest(
        course_markdown="# Body",
        questions=[DrillQuestion.model_validate(_question_payload("q1"))],
        answers=[
            AnswerSubmission(
                id=f"answer-{index}",
                drill_run_id="drill-1",
                learner_name=f"受講者{index}",
                status=AnswerStatus.GRADED,
                answers={"q1": "回答"},
            )
            for index in range(1, answer_count + 1)
        ],
        grading_results=[],
    )


def test_generate_drill_returns_typed_response() -> None:
    client = AgentRuntimeClient(
        invoker=lambda _task_name, _payload: {
            "questions": [_question_payload("q1"), _question_payload("q2"), _question_payload("q3")]
        }
    )

    response = client.generate_drill(
        DrillGenerationRequest(course_title="講座", course_markdown="# Body")
    )

    assert isinstance(response, DrillGenerationResponse)
    assert [question.id for question in response.questions] == ["q1", "q2", "q3"]


def test_schema_validation_failure_is_retried_once() -> None:
    calls = [
        {"questions": [_question_payload("q1")]},
        {"questions": [_question_payload("q1"), _question_payload("q2"), _question_payload("q3")]},
    ]

    client = AgentRuntimeClient(invoker=lambda _task_name, _payload: calls.pop(0))

    response = client.generate_drill(
        DrillGenerationRequest(course_title="講座", course_markdown="# Body")
    )

    assert len(response.questions) == 3
    assert calls == []


def test_schema_validation_failure_after_retry_raises_reason() -> None:
    client = AgentRuntimeClient(invoker=lambda _task_name, _payload: {"questions": []})

    with pytest.raises(AgentInvocationError, match="schema validation failed"):
        client.generate_drill(DrillGenerationRequest(course_title="講座", course_markdown="# Body"))


def test_schema_validation_failure_after_retry_logs_warning_without_response_payload(
    caplog: LogCaptureFixture,
) -> None:
    sentinel = "SECRET_AGENT_RESPONSE_8c74"
    client = AgentRuntimeClient(
        invoker=lambda _task_name, _payload: {"questions": [{"question": sentinel}]}
    )

    with (
        caplog.at_level("WARNING", logger="app.agent"),
        pytest.raises(AgentInvocationError, match="schema validation failed"),
    ):
        client.generate_drill(DrillGenerationRequest(course_title="講座", course_markdown="# Body"))

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "agent response validation failed permanently task=generate_drill" in message
        for message in messages
    )
    assert any("error_type=ValidationError" in message for message in messages)
    assert sentinel not in caplog.text


def test_document_patch_invocation_uses_typed_request_and_response() -> None:
    observed_payloads: list[dict[str, object]] = []

    def invoke(_task_name: str, payload: dict[str, object]) -> dict[str, object]:
        observed_payloads.append(payload)
        return {
            "patchedMarkdown": "# After",
            "patchSummary": "説明を追加",
            "riskNotes": ["要確認"],
        }

    client = AgentRuntimeClient(invoker=invoke)
    response = client.propose_document_patch(
        DocumentPatchRequest(
            course_markdown="# Before",
            failure_signals=[],
        )
    )

    assert isinstance(response, DocumentPatchResponse)
    assert response.patched_markdown == "# After"
    assert observed_payloads[0]["courseMarkdown"] == "# Before"
    assert "courseId" not in observed_payloads[0]


def test_grade_answer_retries_question_id_mismatch_and_recovers() -> None:
    calls = [
        _grading_response_payload("other-question"),
        _grading_response_payload("q1"),
    ]
    client = AgentRuntimeClient(invoker=lambda _task_name, _payload: calls.pop(0))

    response = client.grade_answer(_grading_request("q1"))

    assert isinstance(response, GradingResponse)
    assert response.question_id == "q1"
    assert calls == []


def test_grade_answer_retries_score_exceeding_question_max_and_recovers() -> None:
    calls = [
        _grading_response_payload("q1", score=3),
        _grading_response_payload("q1", score=2),
    ]
    client = AgentRuntimeClient(invoker=lambda _task_name, _payload: calls.pop(0))

    response = client.grade_answer(_grading_request("q1", max_score=2))

    assert response.score == 2
    assert calls == []


def test_grade_answer_context_validation_failure_after_retry_raises() -> None:
    calls = [
        _grading_response_payload("wrong-1"),
        _grading_response_payload("wrong-2"),
    ]
    client = AgentRuntimeClient(invoker=lambda _task_name, _payload: calls.pop(0))

    with pytest.raises(AgentInvocationError, match="schema validation failed"):
        client.grade_answer(_grading_request("q1"))

    assert calls == []


def test_analyze_failures_retries_sample_size_mismatch_and_recovers() -> None:
    calls = [
        {"failureSignals": [_failure_signal_payload(sample_size=1)]},
        {"failureSignals": [_failure_signal_payload(sample_size=2)]},
    ]
    client = AgentRuntimeClient(invoker=lambda _task_name, _payload: calls.pop(0))

    response = client.analyze_failures(_failure_analysis_request(answer_count=2))

    assert isinstance(response, FailureAnalysisResponse)
    assert response.failure_signals[0].affected_count == 1
    assert response.failure_signals[0].sample_size == 2
    assert calls == []


def test_analyze_failures_sample_size_mismatch_after_retry_raises_reason() -> None:
    client = AgentRuntimeClient(
        invoker=lambda _task_name, _payload: {"failureSignals": [_failure_signal_payload(1)]}
    )

    with pytest.raises(AgentInvocationError, match="schema validation failed") as exc_info:
        client.analyze_failures(_failure_analysis_request(answer_count=2))

    assert exc_info.value.reason == "failure signal sampleSize does not match request answers"


def test_agent_invocation_logs_task_latency_and_validation_error(
    caplog: LogCaptureFixture,
) -> None:
    calls: list[dict[str, object]] = [
        {"questions": []},
        {"questions": [_question_payload("q1"), _question_payload("q2"), _question_payload("q3")]},
    ]
    client = AgentRuntimeClient(invoker=lambda _task_name, _payload: calls.pop(0))

    with caplog.at_level("INFO", logger="app.agent"):
        client.generate_drill(DrillGenerationRequest(course_title="講座", course_markdown="# Body"))

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "agent response validation failed task=generate_drill" in message for message in messages
    )
    assert any(
        "agent invocation completed task=generate_drill latency_ms=" in message
        for message in messages
    )
    assert all("# Body" not in message for message in messages)
