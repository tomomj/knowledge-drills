import json
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Scope

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.schemas import DrillQuestion, DrillRun, DrillRunStatus, RubricItem, SourceEvidence
from app.services.answer_service import AnswerService
from app.services.auto_analysis import AutoAnalysisTrigger


class RecordingAutoAnalysisTrigger:
    def __init__(self, events: list[str] | None = None) -> None:
        self.drill_run_ids: list[str] = []
        self._events = events

    def maybe_run(self, drill_run_id: str) -> None:
        self.drill_run_ids.append(drill_run_id)
        if self._events is not None:
            self._events.append("task")


def _install_recording_trigger(
    client: TestClient,
    events: list[str] | None = None,
) -> RecordingAutoAnalysisTrigger:
    trigger = RecordingAutoAnalysisTrigger(events)
    app = cast(FastAPI, client.app)
    app.state.auto_analysis_trigger = cast(AutoAnalysisTrigger, trigger)
    return trigger


def _answer_payload() -> dict[str, object]:
    return {
        "learnerName": "受講者",
        "answers": [
            {"questionId": "q1", "answerText": "短い回答"},
            {"questionId": "q2", "answerText": "短い回答"},
            {"questionId": "q3", "answerText": "短い回答"},
        ],
    }


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
    *,
    status: DrillRunStatus = DrillRunStatus.READY,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=status,
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
        agent_client=AgentRuntimeClient(
            invoker=lambda _task_name, payload: _agent_response_for_question(
                agent_response,
                payload,
            )
        ),
    )


def _agent_response_for_question(
    agent_response: dict[str, object],
    payload: dict[str, object],
) -> dict[str, object]:
    question = cast(dict[str, object], payload["question"])
    return {**agent_response, "questionId": question["id"]}


@pytest.mark.parametrize(
    "path",
    ["/api/drills/share-token/answers", "/api/learn/share-token/answers"],
)
def test_submit_answer_returns_minimal_feedback_without_private_fields(
    client: TestClient,
    path: str,
) -> None:
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
    trigger = _install_recording_trigger(client)

    response = client.post(path, json=_answer_payload())

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
    assert trigger.drill_run_ids == ["drill-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/api/drills/share-token/answers", "/api/learn/share-token/answers"],
)
async def test_submit_answer_starts_background_task_after_response_body_is_sent(
    client: TestClient,
    path: str,
) -> None:
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
    events: list[str] = []
    trigger = _install_recording_trigger(client, events)
    sent_messages: list[Message] = []
    body = json.dumps(_answer_payload()).encode()
    request_messages = [
        {"type": "http.request", "body": body, "more_body": False},
    ]

    async def receive() -> Message:
        if request_messages:
            return request_messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent_messages.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            events.append("body")

    app = cast(FastAPI, client.app)
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)

    start = next(message for message in sent_messages if message["type"] == "http.response.start")
    assert start["status"] == 201
    assert events == ["body", "task"]
    assert trigger.drill_run_ids == ["drill-1"]


@pytest.mark.parametrize("status", [DrillRunStatus.ANALYZING, DrillRunStatus.ANALYZED])
def test_submit_answer_accepts_analysis_lifecycle_statuses(
    client: TestClient,
    status: DrillRunStatus,
) -> None:
    _configure_ready_drill_and_answer_service(
        client,
        {
            "questionId": "q1",
            "score": 3,
            "maxScore": 4,
            "correctPoints": ["判断できている"],
            "missingPoints": ["根拠が不足"],
            "feedback": "根拠を添えてください。",
            "failureTags": ["missing_evidence"],
        },
        status=status,
    )

    response = client.post(
        "/api/drills/share-token/answers",
        json={
            "learnerName": "受講者",
            "answers": [
                {"questionId": "q1", "answerText": "回答1"},
                {"questionId": "q2", "answerText": "回答2"},
                {"questionId": "q3", "answerText": "回答3"},
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "graded"


@pytest.mark.parametrize("status", [DrillRunStatus.GENERATING, DrillRunStatus.FAILED])
def test_submit_answer_rejects_non_distributable_status(
    client: TestClient,
    status: DrillRunStatus,
) -> None:
    _configure_ready_drill_and_answer_service(
        client,
        {
            "questionId": "q1",
            "score": 3,
            "maxScore": 4,
            "correctPoints": ["判断できている"],
            "missingPoints": ["根拠が不足"],
            "feedback": "根拠を添えてください。",
            "failureTags": ["missing_evidence"],
        },
        status=status,
    )

    response = client.post(
        "/api/drills/share-token/answers",
        json={
            "learnerName": "受講者",
            "answers": [
                {"questionId": "q1", "answerText": "回答1"},
                {"questionId": "q2", "answerText": "回答2"},
                {"questionId": "q3", "answerText": "回答3"},
            ],
        },
    )

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_share_token"


@pytest.mark.parametrize(
    "path",
    ["/api/drills/missing-token/answers", "/api/learn/missing-token/answers"],
)
def test_submit_answer_invalid_token_returns_404(client: TestClient, path: str) -> None:
    trigger = _install_recording_trigger(client)

    response = client.post(path, json={"learnerName": "受講者", "answers": []})

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_share_token"
    assert trigger.drill_run_ids == []


@pytest.mark.parametrize(
    "path",
    ["/api/drills/share-token/answers", "/api/learn/share-token/answers"],
)
def test_submit_answer_grading_failure_does_not_schedule_background_task(
    client: TestClient,
    path: str,
) -> None:
    _configure_ready_drill_and_answer_service(client, {})
    trigger = _install_recording_trigger(client)

    response = client.post(path, json=_answer_payload())

    assert response.status_code == 502
    assert response.json()["code"] == "agent_invocation_failed"
    assert trigger.drill_run_ids == []


@pytest.mark.parametrize(
    "path",
    ["/api/drills/share-token/answers", "/api/learn/share-token/answers"],
)
def test_submit_answer_response_is_unchanged_when_background_trigger_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    _configure_ready_drill_and_answer_service(
        client,
        {
            "questionId": "q1",
            "score": 3,
            "maxScore": 4,
            "correctPoints": ["判断できている"],
            "missingPoints": ["根拠が不足"],
            "feedback": "採点結果は維持されます。",
            "failureTags": ["missing_evidence"],
        },
    )
    app = cast(FastAPI, client.app)

    def fail_claim(_drill_run_id: str) -> None:
        raise RuntimeError("claim unavailable")

    monkeypatch.setattr(
        app.state.analysis_execution_repository,
        "claim_auto_analysis",
        fail_claim,
    )

    response = client.post(path, json=_answer_payload())

    assert response.status_code == 201
    assert response.json()["status"] == "graded"
    assert response.json()["feedback"] == [
        "採点結果は維持されます。",
        "採点結果は維持されます。",
        "採点結果は維持されます。",
    ]


@pytest.mark.parametrize(
    "path",
    ["/api/drills/share-token/answers", "/api/learn/share-token/answers"],
)
@pytest.mark.parametrize(
    "learner_name,answer_text",
    [
        ("名" * 51, "回答"),
        ("受講者", "回" * 2_001),
    ],
)
def test_submit_answer_rejects_oversized_text(
    client: TestClient,
    learner_name: str,
    answer_text: str,
    path: str,
) -> None:
    _configure_ready_drill_and_answer_service(
        client,
        {
            "questionId": "q1",
            "score": 3,
            "maxScore": 4,
            "correctPoints": [],
            "missingPoints": [],
            "feedback": "受付しました。",
            "failureTags": [],
        },
    )
    trigger = _install_recording_trigger(client)

    response = client.post(
        path,
        json={
            "learnerName": learner_name,
            "answers": [
                {"questionId": "q1", "answerText": answer_text},
                {"questionId": "q2", "answerText": "回答"},
                {"questionId": "q3", "answerText": "回答"},
            ],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert trigger.drill_run_ids == []
