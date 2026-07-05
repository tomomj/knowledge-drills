from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.services.analysis_service import AnalysisService
from app.services.answer_service import AnswerService
from app.services.drill_service import DrillService
from app.services.share_token_service import ShareTokenService


def _question(question_id: str) -> dict[str, object]:
    return {
        "id": question_id,
        "question": f"{question_id} の判断理由を書いてください。",
        "intent": "判断の根拠を見る",
        "rubric": [{"criterion": "根拠", "points": 4, "required": True}],
        "idealAnswer": "資料の判断基準に基づいて説明する。",
        "sourceEvidence": [{"sectionHeading": "判断基準", "excerpt": "## 判断基準"}],
        "maxScore": 4,
    }


class MvpAgentDouble:
    def __init__(self) -> None:
        self.payloads: list[tuple[str, dict[str, object]]] = []

    def __call__(self, task_name: str, payload: dict[str, object]) -> dict[str, object]:
        self.payloads.append((task_name, payload))
        if task_name == "generate_drill":
            return {"questions": [_question("q1"), _question("q2"), _question("q3")]}
        if task_name == "grade_answer":
            question = cast(dict[str, object], payload["question"])
            return {
                "questionId": question["id"],
                "score": 3,
                "maxScore": 4,
                "correctPoints": ["根拠を示している"],
                "missingPoints": ["例外条件が不足"],
                "feedback": "根拠は明確です。例外条件も添えてください。",
                "failureTags": ["missing_exception"],
            }
        if task_name == "analyze_failures":
            return {
                "failureSignals": [
                    {
                        "id": "fs_integration_001",
                        "title": "例外条件の不足",
                        "severity": "medium",
                        "evidence": ["q2 で例外条件の回答が弱い"],
                        "likelyCause": "資料の例外条件が見つけにくい",
                        "suspectedDocumentGap": "判断基準に例外条件が不足",
                        "targetSections": ["## 判断基準"],
                        "recommendedChange": "例外条件を判断基準に追記する",
                        "sampleSize": 1,
                        "confidenceNote": "少数回答の傾向です。",
                    }
                ]
            }
        if task_name == "propose_document_patch":
            base_markdown = cast(str, payload["courseMarkdown"])
            return {
                "patchedMarkdown": f"{base_markdown}\n\n### 例外条件\n例外時は上長へ確認する。",
                "patchSummary": "例外条件を追記",
                "riskNotes": ["既存ルールとの整合を確認"],
            }
        raise AssertionError(f"unexpected task: {task_name}")


def _configure_agent_backed_services(
    client: TestClient,
    agent: MvpAgentDouble,
) -> None:
    app = cast(FastAPI, client.app)
    agent_client = AgentRuntimeClient(invoker=agent)
    app.state.drill_service = DrillService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=app.state.drill_repository,
            share_token_repository=app.state.share_token_repository,
            token_generator=lambda: "share-token",
        ),
        agent_client=agent_client,
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
    )
    app.state.answer_service = AnswerService(
        drill_repository=app.state.drill_repository,
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
        agent_client=agent_client,
    )
    app.state.analysis_service = AnalysisService(
        app.state.drill_repository,
        app.state.answer_repository,
        course_repository=app.state.course_repository,
        patch_repository=app.state.patch_repository,
        agent_client=agent_client,
    )


def test_full_mvp_flow_from_course_to_patch_apply(client: TestClient) -> None:
    agent = MvpAgentDouble()
    _configure_agent_backed_services(client, agent)

    course_response = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": "# 判断基準\n根拠を確認する。"},
    )
    course_id = course_response.json()["courseId"]

    drill_response = client.post(f"/api/courses/{course_id}/drill-runs")
    assert drill_response.status_code == 201
    drill = drill_response.json()
    drill_run_id = drill["drillRunId"]
    assert drill["shareUrl"] == "/drills/share-token"

    admin_response = client.get(f"/api/courses/{course_id}/drill-runs/{drill_run_id}")
    assert admin_response.status_code == 200
    assert admin_response.json()["answerCount"] == 0

    learner_response = client.get("/api/drills/share-token")
    assert learner_response.status_code == 200
    learner_payload = learner_response.json()
    assert len(learner_payload["questions"]) == 3
    assert "rubric" not in str(learner_payload)
    assert "idealAnswer" not in str(learner_payload)

    answer_response = client.post(
        "/api/drills/share-token/answers",
        json={
            "learnerName": "受講者",
            "answers": [
                {"questionId": "q1", "answerText": "根拠を確認します。"},
                {"questionId": "q2", "answerText": "例外時は確認します。"},
                {"questionId": "q3", "answerText": "次に共有します。"},
            ],
        },
    )
    assert answer_response.status_code == 201
    assert answer_response.json()["status"] == "graded"

    analyzed_admin_response = client.get(f"/api/courses/{course_id}/drill-runs/{drill_run_id}")
    assert analyzed_admin_response.json()["answerCount"] == 1
    assert analyzed_admin_response.json()["canAnalyze"] is True

    analysis_response = client.post(f"/api/courses/{course_id}/drill-runs/{drill_run_id}/analyze")
    assert analysis_response.status_code == 200
    patch_id = analysis_response.json()["patchId"]

    patch_response = client.get(f"/api/patches/{patch_id}")
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "proposed"
    assert patch_response.json()["failureSignals"][0]["confidenceNote"] == "少数回答の傾向です。"

    apply_response = client.post(
        f"/api/patches/{patch_id}/apply",
        json={"ownerFeedback": "反映します"},
    )
    assert apply_response.status_code == 200
    assert apply_response.json()["status"] == "applied"

    updated_course_response = client.get(f"/api/courses/{course_id}")
    updated_course = updated_course_response.json()
    assert updated_course["version"] == 2
    assert "### 例外条件" in updated_course["markdown"]

    serialized_payloads = str(agent.payloads)
    assert "share-token" not in serialized_payloads
    assert "admin token" not in serialized_payloads
    assert "Secret" not in serialized_payloads


def test_stale_patch_and_non_proposed_conflict_return_current_state(client: TestClient) -> None:
    agent = MvpAgentDouble()
    _configure_agent_backed_services(client, agent)
    course_id = client.post(
        "/api/courses",
        json={"title": "講座", "markdown": "# 判断基準\n根拠を確認する。"},
    ).json()["courseId"]
    drill_run_id = client.post(f"/api/courses/{course_id}/drill-runs").json()["drillRunId"]
    client.post(
        "/api/drills/share-token/answers",
        json={
            "learnerName": "受講者",
            "answers": [
                {"questionId": "q1", "answerText": "根拠を確認します。"},
                {"questionId": "q2", "answerText": "例外時は確認します。"},
                {"questionId": "q3", "answerText": "次に共有します。"},
            ],
        },
    )
    patch_id = client.post(f"/api/courses/{course_id}/drill-runs/{drill_run_id}/analyze").json()[
        "patchId"
    ]
    client.put(
        f"/api/courses/{course_id}",
        json={"title": "講座", "markdown": "# 判断基準\n別更新。"},
    )

    stale_response = client.get(f"/api/patches/{patch_id}")
    assert stale_response.status_code == 200
    assert stale_response.json()["status"] == "stale"

    conflict_response = client.post(
        f"/api/patches/{patch_id}/apply",
        json={"ownerFeedback": "反映します"},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["code"] == "patch_not_proposed"
    assert conflict_response.json()["currentStatus"] == "stale"


def test_max_length_course_markdown_save_generate_and_analysis_smoke(
    client: TestClient,
) -> None:
    agent = MvpAgentDouble()
    _configure_agent_backed_services(client, agent)
    course_markdown = "x" * 20_000

    course_response = client.post(
        "/api/courses",
        json={"title": "長い講座", "markdown": course_markdown},
    )
    assert course_response.status_code == 201
    course_id = course_response.json()["courseId"]

    drill_response = client.post(f"/api/courses/{course_id}/drill-runs")
    assert drill_response.status_code == 201
    drill_run_id = drill_response.json()["drillRunId"]

    answer_response = client.post(
        "/api/drills/share-token/answers",
        json={
            "learnerName": "受講者",
            "answers": [
                {"questionId": "q1", "answerText": "根拠を確認します。"},
                {"questionId": "q2", "answerText": "例外時は確認します。"},
                {"questionId": "q3", "answerText": "次に共有します。"},
            ],
        },
    )
    assert answer_response.status_code == 201

    analysis_response = client.post(f"/api/courses/{course_id}/drill-runs/{drill_run_id}/analyze")
    assert analysis_response.status_code == 200
    patch_id = analysis_response.json()["patchId"]
    assert client.get(f"/api/patches/{patch_id}").json()["baseMarkdown"] == course_markdown
