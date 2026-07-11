from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.schemas import (
    AnalysisStepStatus,
    AnalysisTimelineItem,
    AnswerStatus,
    AnswerSubmission,
    Course,
    DrillQuestion,
    DrillRun,
    DrillRunStatus,
    GradingResult,
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
    app.state.share_token_repository.reserve(
        "share-token",
        drill_run_id="drill-1",
        course_id="course-1",
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
    assert payload["needsAnalysis"] is False
    assert payload["questions"][0]["rubric"][0]["criterion"] == "根拠"
    assert payload["rubricSummary"] == ["q1: 根拠"]


def test_get_current_drill_admin_matches_course_list_needs_analysis(
    client: TestClient,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(
            id="course-1",
            owner_user_id="local-owner",
            title="講座",
            markdown="# Body",
            version=2,
        )
    )
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            course_version=2,
            status=DrillRunStatus.READY,
            questions=[_question()],
        )
    )
    for index in range(3):
        app.state.answer_repository.create_submission(
            AnswerSubmission(
                id=f"answer-{index}",
                course_id="course-1",
                drill_run_id="drill-1",
                learner_name=f"受講者{index}",
                status=AnswerStatus.GRADED,
                answers={"q1": "回答"},
                total_score=0,
                max_score=4,
            )
        )

    course_response = client.get("/api/courses")
    drill_response = client.get("/api/courses/course-1/drill-runs/drill-1")

    assert course_response.status_code == 200
    assert drill_response.status_code == 200
    assert course_response.json()["courses"][0]["needsAnalysis"] is True
    assert drill_response.json()["needsAnalysis"] is True
    assert drill_response.json()["canAnalyze"] is True


def test_get_past_drill_admin_never_evaluates_course_needs_analysis(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(
            id="course-1",
            owner_user_id="local-owner",
            title="講座",
            markdown="# Body",
            version=2,
        )
    )
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            course_version=1,
            status=DrillRunStatus.READY,
            questions=[_question()],
        )
    )
    for index in range(3):
        app.state.answer_repository.create_submission(
            AnswerSubmission(
                id=f"answer-{index}",
                course_id="course-1",
                drill_run_id="drill-1",
                learner_name=f"受講者{index}",
                status=AnswerStatus.GRADED,
                answers={"q1": "回答"},
                total_score=0,
                max_score=4,
            )
        )

    def fail_evaluation_read(*_args: object, **_kwargs: object) -> None:
        pytest.fail("past-version admin must not evaluate course needs analysis")

    monkeypatch.setattr(app.state.drill_repository, "list_by_course", fail_evaluation_read)

    response = client.get("/api/courses/course-1/drill-runs/drill-1")

    assert response.status_code == 200
    assert response.json()["needsAnalysis"] is False
    assert response.json()["canAnalyze"] is True


def test_get_current_drill_admin_defaults_needs_analysis_false_without_answer_repository(
    client: TestClient,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(id="course-1", owner_user_id="local-owner", title="講座", markdown="# Body")
    )
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=DrillRunStatus.READY,
            questions=[_question()],
        )
    )
    app.state.drill_service = DrillService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=app.state.drill_repository,
            share_token_repository=app.state.share_token_repository,
        ),
        agent_client=AgentRuntimeClient(invoker=lambda _task_name, _payload: {}),
        answer_repository=None,
        share_token_repository=app.state.share_token_repository,
    )

    response = client.get("/api/courses/course-1/drill-runs/drill-1")

    assert response.status_code == 200
    assert response.json()["needsAnalysis"] is False
    assert response.json()["canAnalyze"] is False


def test_get_drill_admin_applies_owner_guard_before_needs_analysis_reads(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(
            id="course-1",
            owner_user_id="other-owner",
            title="他人の講座",
            markdown="# Body",
        )
    )
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=DrillRunStatus.READY,
            questions=[_question()],
        )
    )

    def fail_related_read(*_args: object, **_kwargs: object) -> None:
        pytest.fail("owner guard must run before answer or needs-analysis reads")

    monkeypatch.setattr(app.state.drill_repository, "list_by_course", fail_related_read)
    monkeypatch.setattr(app.state.answer_repository, "list_by_drill_run", fail_related_read)

    response = client.get("/api/courses/course-1/drill-runs/drill-1")

    assert response.status_code == 404
    assert response.json()["code"] == "drill_run_not_found"


def test_get_drill_admin_returns_score_summary_from_graded_answers_only(
    client: TestClient,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(id="course-1", owner_user_id="local-owner", title="講座", markdown="# Body")
    )
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=DrillRunStatus.READY,
            questions=[_question()],
            drill_focus="例外条件",
            share_token="share-token",
            analysis_timeline=[
                AnalysisTimelineItem(
                    id="collect_answers",
                    title="回答データを収集",
                    status=AnalysisStepStatus.COMPLETED,
                    summary="採点済み回答 2 件",
                    evidence=["平均点 2.5 / 4"],
                )
            ],
        )
    )
    app.state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            course_id="course-1",
            drill_run_id="drill-1",
            learner_name="受講者A",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            grading_results=[
                GradingResult(
                    question_id="q1",
                    score=2,
                    max_score=4,
                    correct_points=["根拠"],
                    missing_points=["例外条件", "確認先"],
                    feedback="例外条件を補ってください。",
                    failure_tags=["missing_exception", "missing_exception", "missing_owner"],
                )
            ],
            total_score=2,
            max_score=4,
        )
    )
    app.state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-2",
            course_id="course-1",
            drill_run_id="drill-1",
            learner_name="受講者B",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            grading_results=[
                GradingResult(
                    question_id="q1",
                    score=3,
                    max_score=4,
                    correct_points=["根拠"],
                    missing_points=["例外条件", "確認先", "判断理由"],
                    feedback="確認先を補ってください。",
                    failure_tags=["missing_owner", "missing_reason"],
                )
            ],
            total_score=3,
            max_score=4,
        )
    )
    app.state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-3",
            course_id="course-1",
            drill_run_id="drill-1",
            learner_name="受講者C",
            status=AnswerStatus.GRADING,
            answers={"q1": "回答"},
        )
    )

    response = client.get("/api/courses/course-1/drill-runs/drill-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["answerCount"] == 3
    assert payload["canAnalyze"] is True
    assert payload["drillFocus"] == "例外条件"
    assert payload["analysisTimeline"][0]["id"] == "collect_answers"
    assert payload["scoreSummary"]["gradedAnswerCount"] == 2
    assert payload["scoreSummary"]["averageScore"] == 2.5
    assert payload["scoreSummary"]["maxScore"] == 4
    question_summary = payload["scoreSummary"]["questions"][0]
    assert question_summary["questionId"] == "q1"
    assert question_summary["gradedAnswerCount"] == 2
    assert question_summary["averageScore"] == 2.5
    assert question_summary["commonMissingPoints"] == ["例外条件", "確認先"]
    assert question_summary["failureTags"] == [
        "missing_owner",
        "missing_exception",
        "missing_reason",
    ]


def test_get_drill_admin_disables_analysis_when_no_graded_answers(
    client: TestClient,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(id="course-1", owner_user_id="local-owner", title="講座", markdown="# Body")
    )
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=DrillRunStatus.READY,
            questions=[_question()],
        )
    )
    app.state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            course_id="course-1",
            drill_run_id="drill-1",
            learner_name="受講者A",
            status=AnswerStatus.GRADING,
            answers={"q1": "回答"},
        )
    )

    response = client.get("/api/courses/course-1/drill-runs/drill-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["answerCount"] == 1
    assert payload["canAnalyze"] is False
    assert payload["needsAnalysis"] is False
    assert payload["scoreSummary"]["gradedAnswerCount"] == 0
    assert payload["scoreSummary"]["averageScore"] is None


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
    course_response = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": "# Body\n\n## 方針\n根拠を確認します。"},
    )
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


def test_generate_new_drill_reuses_public_url_and_keeps_old_run(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    tokens = iter(["stable-token", "unused-token"])
    app.state.drill_service = DrillService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=app.state.drill_repository,
            share_token_repository=app.state.share_token_repository,
            token_generator=tokens.__next__,
        ),
        agent_client=AgentRuntimeClient(invoker=lambda _task_name, _payload: _agent_response()),
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
    )
    course_id = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": "# Body\n\n## 方針\n根拠を確認します。"},
    ).json()["courseId"]

    first = client.post(f"/api/courses/{course_id}/drill-runs").json()
    first_run_id = first["drillRunId"]
    first_answer = client.post(
        "/api/drills/stable-token/answers",
        json={
            "learnerName": "受講者",
            "answers": [
                {"questionId": "q1", "answerText": "回答1"},
                {"questionId": "q2", "answerText": "回答2"},
                {"questionId": "q3", "answerText": "回答3"},
            ],
        },
    )
    assert first_answer.status_code == 201

    second = client.post(f"/api/courses/{course_id}/drill-runs").json()

    assert second["drillRunId"] != first_run_id
    assert second["shareUrl"] == "/drills/stable-token"
    learner = client.get("/api/drills/stable-token")
    assert learner.status_code == 200
    assert learner.json()["drillRunId"] == second["drillRunId"]
    old_admin = client.get(f"/api/courses/{course_id}/drill-runs/{first_run_id}").json()
    assert old_admin["shareStatus"] == "superseded"
    assert old_admin["shareUrl"] is None
    old_answers = client.get(
        f"/api/courses/{course_id}/drill-runs/{first_run_id}/answers"
    ).json()
    assert [answer["learnerName"] for answer in old_answers["answers"]] == ["受講者"]


def test_close_and_reopen_current_share_url(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.drill_service = DrillService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=app.state.drill_repository,
            share_token_repository=app.state.share_token_repository,
            token_generator=lambda: "share-token",
            now=lambda: "2026-07-11T00:00:00+00:00",
        ),
        agent_client=AgentRuntimeClient(invoker=lambda _task_name, _payload: _agent_response()),
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
    )
    course_id = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": "# Body\n\n## 方針\n根拠を確認します。"},
    ).json()["courseId"]
    drill = client.post(f"/api/courses/{course_id}/drill-runs").json()
    drill_run_id = drill["drillRunId"]

    closed = client.post(
        f"/api/courses/{course_id}/drill-runs/{drill_run_id}/share/close"
    )
    assert closed.status_code == 200
    assert closed.json()["shareStatus"] == "closed"
    assert closed.json()["shareUrl"] == "/drills/share-token"
    closed_learner = client.get("/api/drills/share-token")
    assert closed_learner.status_code == 410
    assert closed_learner.headers["cache-control"] == "no-store"
    rejected = client.post(
        "/api/drills/share-token/answers",
        json={"learnerName": "受講者", "answers": []},
    )
    assert rejected.status_code == 410
    assert rejected.json()["code"] == "share_closed"

    reopened = client.post(
        f"/api/courses/{course_id}/drill-runs/{drill_run_id}/share/reopen"
    )
    assert reopened.status_code == 200
    assert reopened.json()["shareStatus"] == "open"
    reopened_learner = client.get("/api/drills/share-token")
    assert reopened_learner.status_code == 200
    assert reopened_learner.headers["cache-control"] == "no-store"


def test_failed_regeneration_keeps_previous_drill_published(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    course_id = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": "# Body\n\n## 方針\n根拠を確認します。"},
    ).json()["courseId"]
    app.state.drill_service = DrillService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=app.state.drill_repository,
            share_token_repository=app.state.share_token_repository,
            token_generator=lambda: "stable-token",
        ),
        agent_client=AgentRuntimeClient(invoker=lambda _task_name, _payload: _agent_response()),
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
    )
    first = client.post(f"/api/courses/{course_id}/drill-runs").json()

    invalid_question = _question().model_copy(
        update={
            "source_evidence": [
                SourceEvidence(section_heading="不存在", excerpt="本文にない根拠")
            ]
        }
    )
    app.state.drill_service = DrillService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=app.state.drill_repository,
            share_token_repository=app.state.share_token_repository,
            token_generator=lambda: "unused-token",
        ),
        agent_client=AgentRuntimeClient(
            invoker=lambda _task_name, _payload: {
                "questions": [
                    invalid_question.model_copy(update={"id": question_id}).model_dump(
                        mode="json", by_alias=True
                    )
                    for question_id in ("q1", "q2", "q3")
                ]
            }
        ),
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
    )

    failed = client.post(f"/api/courses/{course_id}/drill-runs")

    assert failed.status_code == 201
    assert failed.json()["shareUrl"] is None
    learner = client.get("/api/drills/stable-token")
    assert learner.status_code == 200
    assert learner.json()["drillRunId"] == first["drillRunId"]


def test_generate_drill_api_returns_failed_run_for_invalid_source_evidence(
    client: TestClient,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.drill_service = DrillService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=app.state.drill_repository,
            share_token_repository=app.state.share_token_repository,
            token_generator=lambda: "failed-token",
        ),
        agent_client=AgentRuntimeClient(invoker=lambda _task_name, _payload: _agent_response()),
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
    )
    course_response = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": "# Body"},
    )
    course_id = course_response.json()["courseId"]

    response = client.post(f"/api/courses/{course_id}/drill-runs")

    assert response.status_code == 201
    payload = response.json()
    assert payload["drillRunId"]
    assert payload["shareUrl"] == "/drills/failed-token"

    admin_response = client.get(f"/api/courses/{course_id}/drill-runs/{payload['drillRunId']}")
    assert admin_response.status_code == 200
    admin_payload = admin_response.json()
    assert admin_payload["status"] == "failed"
    assert admin_payload["questions"] == []
    assert admin_payload["errorMessage"] == "drill generation failed"

    learner_response = client.get("/api/drills/failed-token")
    assert learner_response.status_code == 404
    assert learner_response.json()["code"] == "invalid_share_token"


@pytest.mark.parametrize("path", ["/api/drills/share-token", "/api/learn/share-token"])
@pytest.mark.parametrize(
    "status",
    [DrillRunStatus.READY, DrillRunStatus.ANALYZING, DrillRunStatus.ANALYZED],
)
def test_get_learner_drill_by_share_token_accepts_analysis_lifecycle_statuses(
    client: TestClient,
    path: str,
    status: DrillRunStatus,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            course_version=2,
            course_title="講座",
            course_markdown="# Body\n\n## 方針\n根拠を確認します。",
            status=status,
            questions=[_question()],
            share_token="share-token",
        )
    )
    app.state.share_token_repository.reserve("share-token", drill_run_id="drill-1")

    response = client.get(path)

    assert response.status_code == 200
    payload = response.json()
    assert payload["drillRunId"] == "drill-1"
    assert payload["courseTitle"] == "講座"
    assert payload["courseMarkdown"] == "# Body\n\n## 方針\n根拠を確認します。"
    assert payload["courseVersion"] == 2
    assert payload["questions"][0]["question"] == "判断理由を書いてください。"
    assert "rubric" not in payload["questions"][0]
    assert "idealAnswer" not in payload["questions"][0]
    assert "sourceEvidence" not in payload["questions"][0]
    assert "intent" not in payload["questions"][0]
    assert "analysisTimeline" not in payload
    assert "drillFocus" not in payload


def test_get_learner_drill_snapshots_course_at_generation_time(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(
            id="course-1",
            owner_user_id="local-owner",
            title="更新後の講座",
            markdown="# 更新後の本文",
            version=2,
        )
    )
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            course_version=1,
            course_title="生成時の講座",
            course_markdown="# 生成時の本文",
            status=DrillRunStatus.READY,
            questions=[_question()],
            share_token="share-token",
        )
    )
    app.state.share_token_repository.reserve("share-token", drill_run_id="drill-1")

    response = client.get("/api/drills/share-token")

    assert response.status_code == 200
    payload = response.json()
    assert payload["courseTitle"] == "生成時の講座"
    assert payload["courseMarkdown"] == "# 生成時の本文"
    assert payload["courseVersion"] == 1


def test_get_learner_drill_falls_back_to_current_course_without_snapshot(
    client: TestClient,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(
            id="course-1",
            owner_user_id="local-owner",
            title="現行の講座",
            markdown="# 現行の本文",
            version=3,
        )
    )
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            course_version=3,
            status=DrillRunStatus.READY,
            questions=[_question()],
            share_token="share-token",
        )
    )
    app.state.share_token_repository.reserve("share-token", drill_run_id="drill-1")

    response = client.get("/api/drills/share-token")

    assert response.status_code == 200
    payload = response.json()
    assert payload["courseTitle"] == "現行の講座"
    assert payload["courseMarkdown"] == "# 現行の本文"
    assert payload["courseVersion"] == 3


@pytest.mark.parametrize("status", [DrillRunStatus.GENERATING, DrillRunStatus.FAILED])
def test_get_learner_drill_by_share_token_rejects_non_distributable_status(
    client: TestClient,
    status: DrillRunStatus,
) -> None:
    app = cast(FastAPI, client.app)
    app.state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id="course-1",
            status=status,
            questions=[_question()],
            share_token="share-token",
        )
    )
    app.state.share_token_repository.reserve("share-token", drill_run_id="drill-1")

    response = client.get("/api/drills/share-token")

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_share_token"


def test_get_learner_drill_invalid_token_returns_404_without_content(client: TestClient) -> None:
    response = client.get("/api/drills/missing-token")

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_share_token"
    assert "questions" not in response.json()
