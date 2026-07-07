from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.schemas import (
    AnswerStatus,
    Course,
    DrillQuestion,
    DrillRun,
    DrillRunStatus,
    RubricItem,
    SourceEvidence,
)
from app.services.drill_service import DrillService
from app.services.share_token_service import ShareTokenService


def _agent_response() -> dict[str, object]:
    return {
        "questions": [
            _question().model_copy(update={"id": "q1"}).model_dump(mode="json", by_alias=True),
            _question().model_copy(update={"id": "q2"}).model_dump(mode="json", by_alias=True),
            _question().model_copy(update={"id": "q3"}).model_dump(mode="json", by_alias=True),
        ]
    }


def _question() -> DrillQuestion:
    return DrillQuestion(
        id="q1",
        question="判断理由を書いてください。",
        intent="判断を見る",
        rubric=[RubricItem(criterion="根拠", points=4)],
        ideal_answer="根拠に基づき判断する。",
        source_evidence=[SourceEvidence(section_heading="方針", excerpt="## 方針")],
        max_score=4,
    )


def test_get_drill_admin_returns_questions_share_url_and_answer_count(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(id="course-1", owner_user_id="local-owner", title="講座", markdown="# Body")
    )
    drill_repository = app.state.drill_repository
    answer_repository = app.state.answer_repository
    drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=DrillRunStatus.READY,
            questions=[_question()],
            share_token="share-token",
        )
    )
    answer_repository.create(
        id="answer-1",
        drill_run_id="drill-1",
        learner_name="受講者",
        status=AnswerStatus.GRADED,
        answers={"q1": "回答"},
    )

    response = client.get("/api/courses/course-1/drill-runs/drill-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "drill-1"
    assert payload["status"] == "ready"
    assert payload["shareUrl"] == "/drills/share-token"
    assert payload["answerCount"] == 1
    assert payload["canAnalyze"] is True
    assert payload["questions"][0]["rubric"][0]["criterion"] == "根拠"
    assert payload["rubricSummary"] == ["q1: 根拠"]


def test_get_drill_admin_returns_not_found(client: TestClient) -> None:
    response = client.get("/api/courses/course-1/drill-runs/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "drill_run_not_found"


def test_generate_drill_api_creates_ready_run_from_course(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.drill_service = DrillService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=app.state.drill_repository,
            share_token_repository=app.state.share_token_repository,
            token_generator=lambda: "generated-token",
        ),
        agent_client=AgentRuntimeClient(invoker=lambda _task_name, _payload: _agent_response()),
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
    )
    course_response = client.post("/api/courses", json={"title": "講座", "markdown": "# Body"})
    course_id = course_response.json()["courseId"]

    response = client.post(f"/api/courses/{course_id}/drill-runs")

    assert response.status_code == 201
    payload = response.json()
    assert payload["drillRunId"]
    assert payload["shareUrl"] == "/drills/generated-token"

    admin_response = client.get(f"/api/courses/{course_id}/drill-runs/{payload['drillRunId']}")
    assert admin_response.status_code == 200
    assert admin_response.json()["status"] == "ready"
    assert len(admin_response.json()["questions"]) == 3

    # 生成したドリルが講座の latestDrillRunId として保存される
    course_after = client.get(f"/api/courses/{course_id}")
    assert course_after.json()["latestDrillRunId"] == payload["drillRunId"]


@pytest.mark.parametrize("path", ["/api/drills/share-token", "/api/learn/share-token"])
def test_get_learner_drill_by_share_token_excludes_private_fields(
    client: TestClient,
    path: str,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=DrillRunStatus.READY,
            questions=[_question()],
            share_token="share-token",
        )
    )
    app.state.share_token_repository.reserve("share-token", drill_run_id="drill-1")

    response = client.get(path)

    assert response.status_code == 200
    payload = response.json()
    assert payload["drillRunId"] == "drill-1"
    assert payload["questions"][0]["question"] == "判断理由を書いてください。"
    assert "rubric" not in payload["questions"][0]
    assert "idealAnswer" not in payload["questions"][0]


def test_get_learner_drill_invalid_token_returns_404_without_content(client: TestClient) -> None:
    response = client.get("/api/drills/missing-token")

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_share_token"
    assert "questions" not in response.json()
