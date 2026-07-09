import pytest
from fastapi.testclient import TestClient

from app.services.demo_seed_data import demo_course_definitions


def test_demo_seed_data_excerpts_and_score_trends_are_consistent() -> None:
    for course in demo_course_definitions():
        markdown_by_version = {
            version: markdown for version, markdown in enumerate(course.markdown_versions, start=1)
        }
        for drill in course.drills:
            markdown = markdown_by_version[drill.course_version]
            for question in drill.questions:
                for evidence in question.source_evidence:
                    assert evidence.excerpt in markdown

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


def test_demo_seed_inserts_two_owned_courses_and_content(client: TestClient) -> None:
    response = client.get("/api/courses")

    assert response.status_code == 200
    courses = {course["title"]: course for course in response.json()["courses"]}
    hackathon = courses["DevOps x AI Agent Hackathon 2026 参加ガイド(デモ)"]
    expense = courses["経費精算の判断基準(デモ・改善 3 周済み)"]
    assert hackathon["isDemo"] is True
    assert hackathon["scoreTrend"] == [
        {"courseVersion": 1, "averageScore": 2.0, "maxScore": 4},
    ]
    assert expense["scoreTrend"] == [
        {"courseVersion": 1, "averageScore": 1.8, "maxScore": 4},
        {"courseVersion": 2, "averageScore": 2.9, "maxScore": 4},
        {"courseVersion": 3, "averageScore": 3.6, "maxScore": 4},
    ]

    hackathon_detail = client.get(f"/api/courses/{hackathon['id']}")
    assert hackathon_detail.status_code == 200
    markdown = hackathon_detail.json()["markdown"]
    drill = client.get(f"/api/courses/{hackathon['id']}/drill-runs/{hackathon['latestDrillRunId']}")
    assert drill.status_code == 200
    drill_payload = drill.json()
    assert drill_payload["canAnalyze"] is True
    assert drill_payload["scoreSummary"]["gradedAnswerCount"] == 4
    for question in drill_payload["questions"]:
        for evidence in question["sourceEvidence"]:
            assert evidence["excerpt"] in markdown

    metrics = client.get(f"/api/courses/{expense['id']}/metrics")
    assert metrics.status_code == 200
    assert [
        run["averageScore"] for run in metrics.json()["runs"] if run["averageScore"] is not None
    ] == [1.8, 2.9, 3.6]
    patch = client.get(f"/api/patches/{expense['latestPatchId']}")
    assert patch.status_code == 200
    assert patch.json()["status"] == "applied"
    assert "+## 例外と期限" in patch.json()["diffText"]


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
