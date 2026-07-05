import pytest
from _pytest.logging import LogCaptureFixture

from app.clients.agent_runtime_client import AgentInvocationError, AgentRuntimeClient
from app.schemas import (
    DocumentPatchRequest,
    DocumentPatchResponse,
    DrillGenerationRequest,
    DrillGenerationResponse,
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
