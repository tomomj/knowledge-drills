from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import CourseRepository
from app.schemas import (
    AnalysisStepStatus,
    AnalysisTimelineItem,
    AnswerStatus,
    AnswerSubmission,
    Course,
    DocumentPatch,
    DrillQuestion,
    DrillRun,
    DrillRunStatus,
    GradingResult,
    PatchStatus,
    RubricItem,
    SourceEvidence,
)
from app.services.answer_service import AnswerService
from app.services.course_service import CourseService


def test_list_courses_seeds_demo_courses_for_new_owner(client: TestClient) -> None:
    response = client.get("/api/courses")

    assert response.status_code == 200
    courses = response.json()["courses"]
    assert len(courses) == 2
    assert {course["title"] for course in courses} == {
        "DevOps x AI Agent Hackathon 2026 参加ガイド(デモ)",
        "経費精算の判断基準(デモ・改善 3 周済み)",
    }
    assert all(course["isDemo"] is True for course in courses)
    needs_analysis_by_title = {
        course["title"]: course["needsAnalysis"] for course in courses
    }
    assert needs_analysis_by_title == {
        "DevOps x AI Agent Hackathon 2026 参加ガイド(デモ)": True,
        "経費精算の判断基準(デモ・改善 3 周済み)": False,
    }


def test_list_courses_defaults_needs_analysis_to_false_without_evaluation_repositories() -> None:
    course_repository = CourseRepository(InMemoryFirestoreClient())
    course_repository.create(
        Course(
            id="course-1",
            owner_user_id="owner-1",
            title="講座",
            markdown="# Body",
        )
    )
    service = CourseService(course_repository)

    response = service.list_courses("owner-1")

    assert response.courses[0].needs_analysis is False


def test_list_courses_recomputes_needs_analysis_without_persisting_it(
    client: TestClient,
) -> None:
    create = client.post("/api/courses", json={"title": "監視対象", "markdown": "# Body"})
    course_id = create.json()["courseId"]
    app_state = client.app.state  # type: ignore[attr-defined]
    app_state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id=course_id,
            course_version=1,
            status=DrillRunStatus.READY,
        )
    )
    first = client.get("/api/courses")
    stored_after_first = app_state.firestore_client.get_document("courses", course_id)
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            drill_run_id="drill-1",
            learner_name="受講者1",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=0,
            max_score=100,
        )
    )
    second = client.get("/api/courses")
    stored_after_second = app_state.firestore_client.get_document("courses", course_id)

    assert first.status_code == 200
    assert first.json()["courses"][0]["needsAnalysis"] is False
    assert second.status_code == 200
    assert second.json()["courses"][0]["needsAnalysis"] is True
    assert stored_after_first is not None
    assert "needsAnalysis" not in stored_after_first
    assert stored_after_second is not None
    assert "needsAnalysis" not in stored_after_second


def test_legacy_analyzed_drill_becomes_needs_analysis_after_one_public_answer(
    client: TestClient,
) -> None:
    create = client.post("/api/courses", json={"title": "Legacy分析済み", "markdown": "# Body"})
    course_id = cast(str, create.json()["courseId"])
    app_state = client.app.state  # type: ignore[attr-defined]
    questions = [
        DrillQuestion(
            id=f"q{index}",
            question="判断理由を書いてください。",
            intent="判断を見る",
            rubric=[RubricItem(criterion="根拠", points=4)],
            ideal_answer="根拠に基づき判断する。",
            source_evidence=[SourceEvidence(section_heading="方針", excerpt="# Body")],
            max_score=4,
        )
        for index in range(1, 4)
    ]
    timeline = [
        AnalysisTimelineItem(
            id="analysis",
            title="分析",
            status=AnalysisStepStatus.COMPLETED,
            completed_at="2026-07-11T00:01:00+00:00",
        )
    ]
    drill_run = DrillRun(
        id="drill-1",
        course_id=course_id,
        course_version=1,
        status=DrillRunStatus.ANALYZED,
        questions=questions,
        analysis_timeline=timeline,
        share_token="share-token",
    )
    app_state.firestore_client.create_document(
        "drill_runs",
        drill_run.id,
        drill_run.model_dump(
            mode="json",
            by_alias=True,
            exclude={"analyzed_answer_count"},
        ),
    )
    raw_legacy = app_state.firestore_client.get_document("drill_runs", drill_run.id)
    assert raw_legacy is not None
    assert "analyzedAnswerCount" not in raw_legacy
    app_state.share_token_repository.reserve("share-token", drill_run_id=drill_run.id)

    def low_score(_task_name: str, payload: dict[str, object]) -> dict[str, object]:
        question = cast(dict[str, object], payload["question"])
        return {
            "questionId": question["id"],
            "score": 0,
            "maxScore": 4,
            "correctPoints": [],
            "missingPoints": ["根拠が不足"],
            "feedback": "根拠を確認してください。",
            "failureTags": ["missing_evidence"],
        }

    app_state.answer_service = AnswerService(
        course_repository=app_state.course_repository,
        drill_repository=app_state.drill_repository,
        answer_repository=app_state.answer_repository,
        share_token_repository=app_state.share_token_repository,
        agent_client=AgentRuntimeClient(invoker=low_score),
    )
    payload = {
        "answers": [
            {"questionId": question.id, "answerText": "短い回答"} for question in questions
        ]
    }

    before_threshold = client.get("/api/courses")
    first = client.post(
        "/api/drills/share-token/answers",
        json={**payload, "learnerName": "受講者1"},
    )
    after_threshold = client.get("/api/courses")

    saved_drill = app_state.drill_repository.get(drill_run.id)
    saved_answers = app_state.answer_repository.list_by_drill_run(drill_run.id)
    assert before_threshold.status_code == 200
    assert before_threshold.json()["courses"][0]["needsAnalysis"] is False
    assert first.status_code == 201
    assert after_threshold.status_code == 200
    assert after_threshold.json()["courses"][0]["needsAnalysis"] is True
    assert saved_drill is not None
    assert saved_drill.analyzed_answer_count == 0
    assert len(saved_answers) - saved_drill.analyzed_answer_count == 1
    assert all(answer.status is AnswerStatus.GRADED for answer in saved_answers)
    assert all(answer.total_score == 0 and answer.max_score == 12 for answer in saved_answers)
    assert saved_drill.status is DrillRunStatus.ANALYZED
    assert saved_drill.analysis_timeline == timeline


def test_list_courses_returns_summaries_sorted_by_updated_at(client: TestClient) -> None:
    first = client.post("/api/courses", json={"title": "先に作成", "markdown": "# A"})
    second = client.post("/api/courses", json={"title": "後に作成", "markdown": "# B"})
    assert first.status_code == 201
    assert second.status_code == 201

    # 先に作った講座を更新して最新にする
    first_id = first.json()["courseId"]
    updated = client.put(f"/api/courses/{first_id}", json={"title": "先に作成", "markdown": "# A2"})
    assert updated.status_code == 200

    response = client.get("/api/courses")

    assert response.status_code == 200
    courses = response.json()["courses"]
    assert [course["title"] for course in courses] == ["先に作成", "後に作成"]
    summary = courses[0]
    assert summary["id"] == first_id
    assert summary["version"] == 2
    assert summary["updatedAt"] is not None
    assert summary["drillStatus"] is None
    assert summary["answerCount"] == 0
    assert summary["patchStatus"] is None
    assert summary["needsAnalysis"] is False
    assert "markdown" not in summary


def test_list_courses_uses_stored_summary_without_related_collection_reads(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create = client.post("/api/courses", json={"title": "状態あり", "markdown": "# Body"})
    course_id = create.json()["courseId"]

    app_state = client.app.state  # type: ignore[attr-defined]
    app_state.course_repository.update_summary(
        course_id,
        latest_drill_run_id="drill-1",
        latest_drill_status=DrillRunStatus.READY,
        answer_count=1,
        latest_patch_id="patch-1",
        latest_patch_status=PatchStatus.PROPOSED,
        score_trend=[],
    )
    app_state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id=course_id,
            course_version=1,
            status=DrillRunStatus.READY,
        )
    )
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            drill_run_id="drill-1",
            learner_name="受講者",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=0,
            max_score=100,
        )
    )

    list_by_course = app_state.drill_repository.list_by_course
    list_by_drill_run = app_state.answer_repository.list_by_drill_run
    drill_list_calls: list[str] = []
    answer_list_calls: list[str] = []

    def observe_drill_list(course_id: str) -> list[DrillRun]:
        drill_list_calls.append(course_id)
        return cast(list[DrillRun], list_by_course(course_id))

    def observe_answer_list(drill_run_id: str) -> list[AnswerSubmission]:
        answer_list_calls.append(drill_run_id)
        return cast(list[AnswerSubmission], list_by_drill_run(drill_run_id))

    def fail_related_read(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("course list should use stored course summary")

    monkeypatch.setattr(app_state.drill_repository, "get", fail_related_read)
    monkeypatch.setattr(app_state.drill_repository, "list_by_course", observe_drill_list)
    monkeypatch.setattr(app_state.answer_repository, "list_by_drill_run", observe_answer_list)
    monkeypatch.setattr(app_state.patch_repository, "get", fail_related_read)
    monkeypatch.setattr(app_state.course_repository, "update_summary", fail_related_read)

    response = client.get("/api/courses")

    assert response.status_code == 200
    summary = response.json()["courses"][0]
    assert summary["drillStatus"] == "ready"
    assert summary["answerCount"] == 1
    assert summary["patchStatus"] == "proposed"
    assert summary["latestDrillRunId"] == "drill-1"
    assert summary["latestPatchId"] == "patch-1"
    assert summary["scoreTrend"] == []
    assert summary["isDemo"] is False
    assert summary["needsAnalysis"] is True
    assert drill_list_calls == [course_id]
    assert answer_list_calls == ["drill-1"]


def test_list_courses_backfills_legacy_summary_fields(client: TestClient) -> None:
    create = client.post("/api/courses", json={"title": "旧データ", "markdown": "# Body"})
    course_id = create.json()["courseId"]

    app_state = client.app.state  # type: ignore[attr-defined]
    app_state.drill_repository.create(
        DrillRun(
            id="drill-1",
            course_id=course_id,
            status=DrillRunStatus.READY,
            share_token="token-1",
        )
    )
    app_state.answer_repository.create(
        id="answer-1",
        drill_run_id="drill-1",
        learner_name="受講者A",
        status=AnswerStatus.GRADED,
        answers={"q1": "回答"},
    )
    app_state.patch_repository.create(
        DocumentPatch(
            id="patch-1",
            course_id=course_id,
            drill_run_id="drill-1",
            status=PatchStatus.PROPOSED,
            base_markdown="# Body",
            patched_markdown="# Body2",
            patch_summary="要約",
            diff_text="-a\n+b",
        )
    )
    course = Course.model_validate(app_state.firestore_client.get_document("courses", course_id))
    app_state.course_repository.update(
        course.model_copy(update={"latest_drill_run_id": "drill-1", "latest_patch_id": "patch-1"})
    )

    response = client.get("/api/courses")

    assert response.status_code == 200
    summary = response.json()["courses"][0]
    assert summary["drillStatus"] == "ready"
    assert summary["answerCount"] == 1
    assert summary["patchStatus"] == "proposed"
    saved_course = app_state.course_repository.get(course_id)
    assert saved_course is not None
    assert saved_course.latest_drill_status == "ready"
    assert saved_course.answer_count == 1
    assert saved_course.latest_patch_status == "proposed"
    assert saved_course.score_trend == []


def test_course_revisions_and_diff(client: TestClient) -> None:
    create = client.post("/api/courses", json={"title": "講座", "markdown": "# v1 本文"})
    course_id = create.json()["courseId"]
    client.put(f"/api/courses/{course_id}", json={"title": "講座", "markdown": "# v2 本文"})
    client.put(f"/api/courses/{course_id}", json={"title": "講座", "markdown": "# v3 本文\n追記"})

    revisions_response = client.get(f"/api/courses/{course_id}/revisions")
    assert revisions_response.status_code == 200
    revisions = revisions_response.json()["revisions"]
    assert [revision["version"] for revision in revisions] == [3, 2, 1]
    assert all(revision["updatedAt"] is not None for revision in revisions)
    assert all("markdown" not in revision for revision in revisions)

    diff_response = client.get(f"/api/courses/{course_id}/revisions/diff?from=2&to=3")
    assert diff_response.status_code == 200
    diff = diff_response.json()
    assert diff["fromVersion"] == 2
    assert diff["toVersion"] == 3
    assert "-# v2 本文" in diff["diffText"]
    assert "+# v3 本文" in diff["diffText"]
    assert "+追記" in diff["diffText"]

    missing = client.get(f"/api/courses/{course_id}/revisions/diff?from=1&to=9")
    assert missing.status_code == 404
    assert missing.json()["code"] == "course_revision_not_found"

    unknown_course = client.get("/api/courses/missing/revisions")
    assert unknown_course.status_code == 404
    assert unknown_course.json()["code"] == "course_not_found"


def test_list_drill_answers_with_grading_results(client: TestClient) -> None:
    create = client.post("/api/courses", json={"title": "講座", "markdown": "# Body"})
    course_id = create.json()["courseId"]

    app_state = client.app.state  # type: ignore[attr-defined]
    drill_run = DrillRun(
        id="drill-1",
        course_id=course_id,
        course_version=2,
        status=DrillRunStatus.READY,
        share_token="token-1",
    )
    app_state.drill_repository.create(drill_run)
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            drill_run_id="drill-1",
            learner_name="受講者A",
            status=AnswerStatus.GRADED,
            answers={"q1": "根拠を書きました"},
            grading_results=[
                GradingResult(
                    question_id="q1",
                    score=3,
                    max_score=4,
                    feedback="根拠は明確です。例外条件を添えてください。",
                )
            ],
            total_score=3,
            max_score=4,
        )
    )

    response = client.get(f"/api/courses/{course_id}/drill-runs/drill-1/answers")

    assert response.status_code == 200
    body = response.json()
    assert body["courseVersion"] == 2
    assert len(body["answers"]) == 1
    answer = body["answers"][0]
    assert answer["learnerName"] == "受講者A"
    assert answer["status"] == "graded"
    assert answer["totalScore"] == 3
    assert answer["answers"]["q1"] == "根拠を書きました"
    assert answer["gradingResults"][0]["feedback"] == "根拠は明確です。例外条件を添えてください。"

    mismatched = client.get("/api/courses/other-course/drill-runs/drill-1/answers")
    assert mismatched.status_code == 404


def test_get_course_metrics_returns_run_level_score_history(client: TestClient) -> None:
    create = client.post("/api/courses", json={"title": "講座", "markdown": "# Body"})
    course_id = create.json()["courseId"]

    app_state = client.app.state  # type: ignore[attr-defined]
    app_state.drill_repository.create(
        DrillRun(
            id="drill-v1",
            course_id=course_id,
            course_version=1,
            status=DrillRunStatus.ANALYZED,
            questions=[_question("q1")],
        )
    )
    app_state.drill_repository.create(
        DrillRun(
            id="drill-v2",
            course_id=course_id,
            course_version=2,
            status=DrillRunStatus.READY,
            questions=[_question("q1"), _question("q2")],
        )
    )
    app_state.drill_repository.create(
        DrillRun(
            id="drill-no-graded",
            course_id=course_id,
            course_version=3,
            status=DrillRunStatus.READY,
            questions=[_question("q1")],
        )
    )
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-v1-graded",
            drill_run_id="drill-v1",
            learner_name="受講者A",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=2,
            max_score=4,
        )
    )
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-v1-failed",
            drill_run_id="drill-v1",
            learner_name="受講者B",
            status=AnswerStatus.FAILED,
            answers={"q1": "回答"},
        )
    )
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-v2-1",
            drill_run_id="drill-v2",
            learner_name="受講者C",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答", "q2": "回答"},
            total_score=6,
            max_score=8,
        )
    )
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-v2-2",
            drill_run_id="drill-v2",
            learner_name="受講者D",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答", "q2": "回答"},
            total_score=8,
            max_score=8,
        )
    )
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-no-graded",
            drill_run_id="drill-no-graded",
            learner_name="受講者E",
            status=AnswerStatus.FAILED,
            answers={"q1": "回答"},
        )
    )

    response = client.get(f"/api/courses/{course_id}/metrics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["courseId"] == course_id
    assert payload["runs"] == [
        {
            "drillRunId": "drill-v1",
            "courseVersion": 1,
            "answerCount": 2,
            "averageScore": 2.0,
            "maxScore": 4,
        },
        {
            "drillRunId": "drill-v2",
            "courseVersion": 2,
            "answerCount": 2,
            "averageScore": 7.0,
            "maxScore": 8,
        },
        {
            "drillRunId": "drill-no-graded",
            "courseVersion": 3,
            "answerCount": 1,
            "averageScore": None,
            "maxScore": 4,
        },
    ]


def test_course_summary_score_trend_backfill_matches_metrics(client: TestClient) -> None:
    create = client.post("/api/courses", json={"title": "講座", "markdown": "# Body"})
    course_id = create.json()["courseId"]

    app_state = client.app.state  # type: ignore[attr-defined]
    app_state.drill_repository.create(
        DrillRun(
            id="drill-v1",
            course_id=course_id,
            course_version=1,
            status=DrillRunStatus.READY,
            questions=[_question("q1")],
        )
    )
    app_state.drill_repository.create(
        DrillRun(
            id="drill-v2",
            course_id=course_id,
            course_version=2,
            status=DrillRunStatus.READY,
            questions=[_question("q1")],
        )
    )
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-v1",
            drill_run_id="drill-v1",
            learner_name="受講者A",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=2,
            max_score=4,
        )
    )
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-v2",
            drill_run_id="drill-v2",
            learner_name="受講者B",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=3,
            max_score=4,
        )
    )
    app_state.course_repository.update_summary(course_id, answer_count=2)

    list_response = client.get("/api/courses")
    metrics_response = client.get(f"/api/courses/{course_id}/metrics")

    assert list_response.status_code == 200
    assert metrics_response.status_code == 200
    summary = list_response.json()["courses"][0]
    metric_runs = metrics_response.json()["runs"]
    assert summary["scoreTrend"] == [
        {
            "courseVersion": run["courseVersion"],
            "averageScore": run["averageScore"],
            "maxScore": run["maxScore"],
        }
        for run in metric_runs
    ]
    saved = app_state.course_repository.get(course_id)
    assert saved is not None
    assert saved.score_trend is not None


def test_delete_course_cascades_related_documents(client: TestClient) -> None:
    create = client.post("/api/courses", json={"title": "削除対象", "markdown": "# Body"})
    course_id = create.json()["courseId"]

    app_state = client.app.state  # type: ignore[attr-defined]
    drill_run = DrillRun(
        id="drill-1",
        course_id=course_id,
        status=DrillRunStatus.READY,
        share_token="token-1",
        questions=[_question("q1")],
    )
    app_state.drill_repository.create(drill_run)
    app_state.share_token_repository.reserve("token-1", "drill-1")
    app_state.answer_repository.create_submission(
        AnswerSubmission(
            id="answer-1",
            drill_run_id="drill-1",
            learner_name="受講者A",
            status=AnswerStatus.GRADED,
            answers={"q1": "回答"},
            total_score=3,
            max_score=4,
        )
    )
    app_state.patch_repository.create(
        DocumentPatch(
            id="patch-1",
            course_id=course_id,
            drill_run_id="drill-1",
            status=PatchStatus.PROPOSED,
            base_markdown="# Body",
            patched_markdown="# Body\n\n追記",
            patch_summary="追記",
            diff_text="+追記",
        )
    )

    response = client.delete(f"/api/courses/{course_id}")

    assert response.status_code == 204
    assert client.get(f"/api/courses/{course_id}").status_code == 404
    assert client.get(f"/api/courses/{course_id}/drill-runs/drill-1").status_code == 404
    assert client.get("/api/patches/patch-1").status_code == 404
    assert client.get("/api/drills/token-1").status_code == 404
    assert client.delete(f"/api/courses/{course_id}").status_code == 404
    listed = client.get("/api/courses")
    assert listed.status_code == 200
    assert course_id not in {course["id"] for course in listed.json()["courses"]}
    assert app_state.answer_repository.get("answer-1") is None
    assert app_state.drill_repository.get("drill-1") is None
    assert app_state.patch_repository.get("patch-1") is None
    assert app_state.course_repository.get_revision(course_id, 1) is None


def test_delete_course_owned_by_other_user_returns_not_found(client: TestClient) -> None:
    app_state = client.app.state  # type: ignore[attr-defined]
    app_state.course_repository.create(
        Course(
            id="other-course",
            owner_user_id="other-owner",
            title="他人の講座",
            markdown="# Body",
        )
    )

    response = client.delete("/api/courses/other-course")

    assert response.status_code == 404
    assert response.json()["code"] == "course_not_found"
    assert app_state.course_repository.get("other-course") is not None


def test_create_get_and_update_course(client: TestClient) -> None:
    create_response = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": "# Body"},
    )

    assert create_response.status_code == 201
    course_id = create_response.json()["courseId"]

    get_response = client.get(f"/api/courses/{course_id}")
    assert get_response.status_code == 200
    course = get_response.json()
    assert course["id"] == course_id
    assert course["title"] == "講座"
    assert course["markdown"] == "# Body"
    assert course["version"] == 1
    assert course["latestDrillRunId"] is None
    assert course["latestPatchId"] is None

    update_response = client.put(
        f"/api/courses/{course_id}",
        json={"title": "更新", "markdown": "# Updated"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["title"] == "更新"
    assert updated["markdown"] == "# Updated"
    assert updated["version"] == 2


def test_course_drill_focus_is_saved_normalized_versioned_and_not_listed(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/courses",
        json={
            "title": "講座",
            "markdown": "# Body",
            "drillFocus": "  例外条件を重点的に出す  ",
        },
    )
    assert create_response.status_code == 201
    course_id = create_response.json()["courseId"]

    detail_response = client.get(f"/api/courses/{course_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["drillFocus"] == "例外条件を重点的に出す"
    assert detail["version"] == 1

    list_response = client.get("/api/courses")
    assert list_response.status_code == 200
    summary = list_response.json()["courses"][0]
    assert "drillFocus" not in summary

    app_state = client.app.state  # type: ignore[attr-defined]
    revision_v1 = app_state.course_repository.get_revision(course_id, 1)
    assert revision_v1 is not None
    assert revision_v1.drill_focus == "例外条件を重点的に出す"

    update_response = client.put(
        f"/api/courses/{course_id}",
        json={
            "title": "講座",
            "markdown": "# Body",
            "drillFocus": "業務上の判断基準",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["version"] == 2
    assert updated["drillFocus"] == "業務上の判断基準"
    revision_v2 = app_state.course_repository.get_revision(course_id, 2)
    assert revision_v2 is not None
    assert revision_v2.drill_focus == "業務上の判断基準"

    clear_response = client.put(
        f"/api/courses/{course_id}",
        json={"title": "講座", "markdown": "# Body", "drillFocus": "   "},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["version"] == 3
    assert clear_response.json()["drillFocus"] is None
    revision_v3 = app_state.course_repository.get_revision(course_id, 3)
    assert revision_v3 is not None
    assert revision_v3.drill_focus is None


def test_course_validation_errors(client: TestClient) -> None:
    empty_title = client.post("/api/courses", json={"title": "", "markdown": "# Body"})
    empty_markdown = client.post("/api/courses", json={"title": "講座", "markdown": ""})
    too_long = client.post("/api/courses", json={"title": "講座", "markdown": "x" * 20001})
    too_long_focus = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": "# Body", "drillFocus": "あ" * 501},
    )

    assert empty_title.status_code == 400
    assert empty_title.json()["code"] == "course_title_required"
    assert empty_markdown.status_code == 400
    assert empty_markdown.json()["code"] == "course_markdown_required"
    assert too_long.status_code == 400
    assert too_long.json()["code"] == "course_markdown_too_long"
    assert too_long_focus.status_code == 422
    assert too_long_focus.json()["code"] == "validation_error"


def test_update_missing_course_returns_not_found(client: TestClient) -> None:
    response = client.put(
        "/api/courses/missing-course",
        json={"title": "講座", "markdown": "# Body"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "course_not_found"


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
