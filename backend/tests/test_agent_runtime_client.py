import pytest
from _pytest.logging import LogCaptureFixture

from app.clients.agent_runtime_client import AgentInvocationError, AgentRuntimeClient
from app.schemas import (
    DocumentPatchRequest,
    DocumentPatchResponse,
    DrillGenerationRequest,
    DrillGenerationResponse,
    DrillQuestion,
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
