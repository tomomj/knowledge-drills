import pytest
from fastapi.testclient import TestClient
from knowledge_drill_agent.schemas import (
    FailureAnalysisInput as AgentFailureAnalysisInput,
)
from knowledge_drill_agent.schemas import GradingInput as AgentGradingInput
from knowledge_drill_agent.schemas import GradingOutput as AgentGradingOutput

from app.services.demo_seed_data import demo_course_definitions


def test_demo_seed_data_excerpts_and_score_trends_are_consistent() -> None:
    for course in demo_course_definitions():
        markdown_by_version = {
            version: markdown for version, markdown in enumerate(course.markdown_versions, start=1)
        }
        for drill in course.drills:
            markdown = markdown_by_version[drill.course_version]
            assert len(drill.questions) == 3
            for question in drill.questions:
                assert question.max_score == 4
                assert sum(item.points for item in question.rubric) == 4
                for evidence in question.source_evidence:
                    assert evidence.excerpt in markdown

                AgentGradingInput.model_validate(
                    {
                        "question": question.model_dump(mode="json", by_alias=True),
                        "learnerAnswer": "確認回答",
                    }
                )

            max_score = sum(question.max_score for question in drill.questions)
            question_ids = {question.id for question in drill.questions}
            for answer in drill.answers:
                seeded_answers = dict(answer.answers_by_question)
                assert set(seeded_answers) == question_ids
                assert len(set(seeded_answers.values())) == len(question_ids)
                assert {result.question_id for result in answer.grading_results} == question_ids
                assert answer.total_score == sum(result.score for result in answer.grading_results)
            analysis_payload = {
                "courseMarkdown": markdown,
                "questions": [
                    question.model_dump(mode="json", by_alias=True) for question in drill.questions
                ],
                "answers": [
                    {
                        "learnerName": answer.learner_name,
                        "totalScore": answer.total_score,
                        "maxScore": max_score,
                        "gradingResults": [
                            result.model_dump(mode="json", by_alias=True)
                            for result in answer.grading_results
                        ],
                    }
                    for answer in drill.answers
                ],
                "gradingResults": [
                    result.model_dump(mode="json", by_alias=True)
                    for answer in drill.answers
                    for result in answer.grading_results
                ],
            }
            AgentFailureAnalysisInput.model_validate(analysis_payload)
            for result in analysis_payload["gradingResults"]:
                AgentGradingOutput.model_validate(result)

        actual_scores = []
        for drill in course.drills:
            max_score = sum(question.max_score for question in drill.questions)
            average_score = sum(answer.total_score for answer in drill.answers) / len(drill.answers)
            actual_scores.append(
                {
                    "courseVersion": drill.course_version,
                    "averageScore": average_score,
                    "maxScore": max_score,
                }
            )

        assert actual_scores == [
            point.model_dump(mode="json", by_alias=True) for point in course.score_trend
        ]


def test_latest_demo_share_urls_accept_answers_through_normal_runtime_contract(
    client: TestClient,
) -> None:
    courses = client.get("/api/courses").json()["courses"]

    for course in courses:
        drill = client.get(
            f"/api/courses/{course['id']}/drill-runs/{course['latestDrillRunId']}"
        ).json()
        share_token = drill["shareUrl"].rsplit("/", maxsplit=1)[-1]
        learner = client.get(f"/api/drills/{share_token}").json()

        response = client.post(
            f"/api/drills/{share_token}/answers",
            json={
                "learnerName": "seed契約確認",
                "answers": [
                    {
                        "questionId": question["id"],
                        "answerText": "教材の根拠に基づいて判断します。",
                    }
                    for question in learner["questions"]
                ],
            },
        )

        assert response.status_code == 201
        assert response.json()["status"] == "graded"
        assert len(response.json()["feedback"]) == 3


def test_hackathon_third_answer_triggers_automatic_analysis_and_patch(
    client: TestClient,
) -> None:
    courses = client.get("/api/courses").json()["courses"]
    course = next(
        item
        for item in courses
        if item["title"] == "DevOps x AI Agent Hackathon 2026 参加ガイド(デモ)"
    )
    drill_url = f"/api/courses/{course['id']}/drill-runs/{course['latestDrillRunId']}"
    drill = client.get(drill_url).json()
    share_token = drill["shareUrl"].rsplit("/", maxsplit=1)[-1]
    learner = client.get(f"/api/drills/{share_token}").json()

    response = client.post(
        f"/api/drills/{share_token}/answers",
        json={
            "learnerName": "自動分析契約確認",
            "answers": [
                {
                    "questionId": question["id"],
                    "answerText": "教材の根拠に基づいて判断します。",
                }
                for question in learner["questions"]
            ],
        },
    )

    assert response.status_code == 201
    analyzed = client.get(drill_url).json()
    assert analyzed["status"] == "analyzed"
    assert analyzed["analysisOrigin"] == "automatic"
    assert analyzed["latestPatchId"] is not None
    patch = client.get(f"/api/patches/{analyzed['latestPatchId']}")
    assert patch.status_code == 200
    assert patch.json()["analysisOrigin"] == "automatic"


def test_demo_seed_inserts_two_owned_courses_and_content(client: TestClient) -> None:
    response = client.get("/api/courses")

    assert response.status_code == 200
    courses = {course["title"]: course for course in response.json()["courses"]}
    hackathon = courses["DevOps x AI Agent Hackathon 2026 参加ガイド(デモ)"]
    expense = courses["経費精算の判断基準(デモ・改善 3 周済み)"]
    assert hackathon["isDemo"] is True
    assert hackathon["scoreTrend"] == [
        {"courseVersion": 1, "averageScore": 6.0, "maxScore": 12},
    ]
    assert expense["scoreTrend"] == [
        {"courseVersion": 1, "averageScore": 5.4, "maxScore": 12},
        {"courseVersion": 2, "averageScore": 8.7, "maxScore": 12},
        {"courseVersion": 3, "averageScore": 10.8, "maxScore": 12},
    ]

    hackathon_detail = client.get(f"/api/courses/{hackathon['id']}")
    assert hackathon_detail.status_code == 200
    markdown = hackathon_detail.json()["markdown"]
    drill = client.get(f"/api/courses/{hackathon['id']}/drill-runs/{hackathon['latestDrillRunId']}")
    assert drill.status_code == 200
    drill_payload = drill.json()
    assert drill_payload["canAnalyze"] is True
    assert drill_payload["scoreSummary"]["gradedAnswerCount"] == 2
    for question in drill_payload["questions"]:
        for evidence in question["sourceEvidence"]:
            assert evidence["excerpt"] in markdown

    metrics = client.get(f"/api/courses/{expense['id']}/metrics")
    assert metrics.status_code == 200
    assert [
        run["averageScore"] for run in metrics.json()["runs"] if run["averageScore"] is not None
    ] == [5.4, 8.7, 10.8]
    patch = client.get(f"/api/patches/{expense['latestPatchId']}")
    assert patch.status_code == 200
    assert patch.json()["status"] == "applied"
    assert "+## 例外と期限" in patch.json()["diffText"]


def test_demo_seed_drill_runs_snapshot_version_matched_course(client: TestClient) -> None:
    courses = {course["title"]: course for course in client.get("/api/courses").json()["courses"]}
    definitions = {definition.title: definition for definition in demo_course_definitions()}

    for title, definition in definitions.items():
        course = courses[title]
        app_state = client.app.state  # type: ignore[attr-defined]
        drill_runs = {
            drill_run.course_version: drill_run
            for drill_run in app_state.drill_repository.list_by_course(course["id"])
        }
        for drill in definition.drills:
            drill_run = drill_runs[drill.course_version]
            assert drill_run.course_title == definition.title
            assert (
                drill_run.course_markdown
                == (definition.markdown_versions[drill.course_version - 1])
            )

            learner = client.get(f"/api/drills/{drill_run.share_token}")
            is_latest = drill is definition.drills[-1]
            assert learner.status_code == (200 if is_latest else 410)
            if not is_latest:
                assert learner.json()["code"] == "share_closed"
                continue
            payload = learner.json()
            assert payload["courseTitle"] == definition.title
            assert (
                payload["courseMarkdown"]
                == (definition.markdown_versions[drill.course_version - 1])
            )
            assert payload["courseVersion"] == drill.course_version


def test_demo_seed_is_once_only_even_after_me_and_deletion(client: TestClient) -> None:
    seeded = client.get("/api/courses").json()["courses"]

    assert client.get("/api/me").status_code == 200
    for course in seeded:
        assert client.delete(f"/api/courses/{course['id']}").status_code == 204

    response = client.get("/api/courses")

    assert response.status_code == 200
    assert response.json() == {"courses": []}


def test_demo_seed_skips_owner_with_existing_course(client: TestClient) -> None:
    created = client.post("/api/courses", json={"title": "自分の講座", "markdown": "# Body"})
    assert created.status_code == 201

    response = client.get("/api/courses")

    assert response.status_code == 200
    courses = response.json()["courses"]
    assert [course["title"] for course in courses] == ["自分の講座"]
    assert courses[0]["isDemo"] is False


def test_course_list_still_succeeds_when_demo_seed_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_seed(_owner_user_id: str) -> None:
        raise RuntimeError("seed failed")

    app_state = client.app.state  # type: ignore[attr-defined]
    monkeypatch.setattr(app_state.demo_seed_service, "ensure_seeded", fail_seed)

    response = client.get("/api/courses")

    assert response.status_code == 200
    assert response.json() == {"courses": []}
