from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.schemas import DrillQuestion, DrillRun, DrillRunStatus, RubricItem, SourceEvidence
from app.services.answer_service import AnswerService


def _question(question_id: str) -> DrillQuestion:
    return DrillQuestion(
        id=question_id,
        question="判断理由を書いてください。",
        intent="判断を見る",
        rubric=[RubricItem(criterion="根拠", points=4)],
        ideal_answer="根拠に基づき判断する。",
        source_evidence=[SourceEvidence(section_heading="方針", excerpt="## 方針")],
        max_score=4,
    )


def _configure_ready_drill_and_answer_service(
    client: TestClient,
    agent_response: dict[str, object],
) -> None:
    app = cast(FastAPI, client.app)
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=DrillRunStatus.READY,
            questions=[
                _question("q1"),
                _question("q2"),
                _question("q3"),
            ],
            share_token="share-token",
        )
    )
    app.state.share_token_repository.reserve("share-token", drill_run_id="drill-1")
    app.state.answer_service = AnswerService(
        drill_repository=app.state.drill_repository,
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
        agent_client=AgentRuntimeClient(invoker=lambda _task_name, _payload: agent_response),
    )


def test_submit_answer_returns_minimal_feedback_without_private_fields(client: TestClient) -> None:
    _configure_ready_drill_and_answer_service(
        client,
        {
            "questionId": "q1",
            "score": 3,
            "maxScore": 4,
            "correctPoints": ["判断できている"],
            "missingPoints": ["根拠が不足"],
            "feedback": "根拠を添えるとさらに良くなります。",
            "failureTags": ["missing_evidence"],
        },
    )

    response = client.post(
        "/api/drills/share-token/answers",
        json={
            "learnerName": "受講者",
            "answers": [
                {"questionId": "q1", "answerText": "短い回答"},
                {"questionId": "q2", "answerText": "短い回答"},
                {"questionId": "q3", "answerText": "短い回答"},
            ],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "graded"
    assert payload["feedback"] == [
        "根拠を添えるとさらに良くなります。",
        "根拠を添えるとさらに良くなります。",
        "根拠を添えるとさらに良くなります。",
    ]
    assert "rubric" not in str(payload)
    assert "idealAnswer" not in str(payload)


def test_submit_answer_invalid_token_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/drills/missing-token/answers",
        json={"learnerName": "受講者", "answers": []},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_share_token"
