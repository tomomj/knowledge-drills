from collections.abc import Callable
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.repositories.repositories import DrillRepository
from app.schemas import (
    AnswerStatus,
    AnswerSubmission,
    Course,
    DocumentPatch,
    DrillQuestion,
    DrillRun,
    DrillRunStatus,
    PatchStatus,
    RubricItem,
    SourceEvidence,
)
from app.services.answer_service import AnswerService


def _question(question_id: str) -> DrillQuestion:
    return DrillQuestion(
        id=question_id,
        question="判断理由を書いてください。",
        intent="判断を見る",
        rubric=[RubricItem(criterion="根拠", points=4)],
        ideal_answer="根拠に基づき判断する。",
        source_evidence=[SourceEvidence(section_heading="方針", excerpt="# Body")],
        max_score=4,
    )


def _seed_legacy_drill(
    client: TestClient,
    *,
    status: DrillRunStatus,
    analyzed_answer_count: int | None,
    answer_count: int,
    share_token: str | None = None,
) -> tuple[FastAPI, str, str]:
    app = cast(FastAPI, client.app)
    course_id = "legacy-course"
    drill_run_id = "legacy-drill"
    app.state.course_repository.create(
        Course(
            id=course_id,
            owner_user_id="local-owner",
            title="Legacy講座",
            markdown="# Body",
        )
    )
    drill_run = DrillRun(
        id=drill_run_id,
        course_id=course_id,
        course_version=1,
        status=status,
        questions=[_question(f"q{index}") for index in range(1, 4)],
        share_token=share_token,
    )
    raw_drill = drill_run.model_dump(mode="json", by_alias=True)
    raw_drill.pop("analyzedAnswerCount")
    raw_drill.pop("autoAnalyzedScoredAnswerCount")
    if analyzed_answer_count is not None:
        raw_drill["analyzedAnswerCount"] = analyzed_answer_count
    app.state.firestore_client.set_document(
        DrillRepository.collection,
        drill_run_id,
        raw_drill,
    )
    if share_token is not None:
        app.state.share_token_repository.reserve(share_token, drill_run_id=drill_run_id)
    for index in range(answer_count):
        app.state.answer_repository.create_submission(
            AnswerSubmission(
                id=f"legacy-answer-{index}",
                course_id=course_id,
                drill_run_id=drill_run_id,
                learner_name=f"受講者{index}",
                status=AnswerStatus.GRADED,
                answers={"q1": "回答"},
                total_score=0,
                max_score=12,
            )
        )
    return app, course_id, drill_run_id


def _course_needs_analysis(client: TestClient, course_id: str) -> bool:
    response = client.get("/api/courses")
    assert response.status_code == 200
    summary = next(course for course in response.json()["courses"] if course["id"] == course_id)
    return cast(bool, summary["needsAnalysis"])


@pytest.mark.parametrize(
    ("legacy_count", "scored_count", "claim_expected"),
    [(2, 7, True), (9, 5, False)],
)
def test_auto_claim_uses_capped_legacy_watermark_from_raw_document(
    client: TestClient,
    legacy_count: int,
    scored_count: int,
    claim_expected: bool,
) -> None:
    app, course_id, drill_run_id = _seed_legacy_drill(
        client,
        status=DrillRunStatus.READY,
        analyzed_answer_count=legacy_count,
        answer_count=scored_count,
    )

    raw_before = app.state.firestore_client.get_document(
        DrillRepository.collection,
        drill_run_id,
    )
    model_before = app.state.drill_repository.get(drill_run_id)
    assert raw_before is not None
    assert raw_before["analyzedAnswerCount"] == legacy_count
    assert "autoAnalyzedScoredAnswerCount" not in raw_before
    assert model_before is not None
    assert model_before.analyzed_answer_count == legacy_count
    assert model_before.auto_analyzed_scored_answer_count is None
    assert _course_needs_analysis(client, course_id) is True

    claim = app.state.analysis_execution_repository.claim_auto_analysis(drill_run_id)

    assert (claim is not None) is claim_expected
    if claim is not None:
        assert claim.snapshot_scored_answer_count == scored_count
        assert set(claim.answer_ids) == {
            f"legacy-answer-{index}" for index in range(scored_count)
        }
    else:
        assert app.state.drill_repository.get(drill_run_id) == model_before


@pytest.mark.parametrize(
    ("status", "claim_expected", "needs_analysis"),
    [
        (DrillRunStatus.READY, True, True),
        (DrillRunStatus.ANALYZED, False, False),
    ],
)
def test_missing_both_watermarks_uses_status_specific_baseline_through_reads_and_claim(
    client: TestClient,
    status: DrillRunStatus,
    claim_expected: bool,
    needs_analysis: bool,
) -> None:
    app, course_id, drill_run_id = _seed_legacy_drill(
        client,
        status=status,
        analyzed_answer_count=None,
        answer_count=5,
    )

    raw = app.state.firestore_client.get_document(DrillRepository.collection, drill_run_id)
    model = app.state.drill_repository.get(drill_run_id)
    assert raw is not None
    assert "analyzedAnswerCount" not in raw
    assert "autoAnalyzedScoredAnswerCount" not in raw
    assert model is not None
    assert model.analyzed_answer_count is None
    assert model.auto_analyzed_scored_answer_count is None
    assert _course_needs_analysis(client, course_id) is needs_analysis

    claim = app.state.analysis_execution_repository.claim_auto_analysis(drill_run_id)

    assert (claim is not None) is claim_expected


def _low_score_agent(_task_name: str, payload: dict[str, object]) -> dict[str, object]:
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


@pytest.mark.parametrize(
    "path",
    ["/api/drills/legacy-token/answers", "/api/learn/legacy-token/answers"],
)
def test_legacy_analyzed_submit_lazily_initializes_before_save_and_leaves_only_new_delta(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    app, course_id, drill_run_id = _seed_legacy_drill(
        client,
        status=DrillRunStatus.ANALYZED,
        analyzed_answer_count=None,
        answer_count=4,
        share_token="legacy-token",
    )
    app.state.answer_service = AnswerService(
        course_repository=app.state.course_repository,
        drill_repository=app.state.drill_repository,
        answer_repository=app.state.answer_repository,
        share_token_repository=app.state.share_token_repository,
        agent_client=AgentRuntimeClient(invoker=_low_score_agent),
    )
    persistence_events: list[tuple[str, int, int | None]] = []
    original_initialize = app.state.drill_repository.initialize_analyzed_answer_count
    original_create_submission = app.state.answer_repository.create_submission

    def record_initialize(target_drill_run_id: str, baseline: int) -> None:
        existing_count = len(
            app.state.answer_repository.list_by_drill_run(target_drill_run_id)
        )
        original_initialize(target_drill_run_id, baseline)
        raw = app.state.firestore_client.get_document(
            DrillRepository.collection,
            target_drill_run_id,
        )
        assert raw is not None
        persisted_baseline = cast(int | None, raw.get("analyzedAnswerCount"))
        persistence_events.append(
            ("initialize_complete", existing_count, persisted_baseline)
        )

    def record_create_submission(answer: AnswerSubmission) -> None:
        raw = app.state.firestore_client.get_document(
            DrillRepository.collection,
            answer.drill_run_id,
        )
        assert raw is not None
        existing_count = len(
            app.state.answer_repository.list_by_drill_run(answer.drill_run_id)
        )
        persistence_events.append(
            (
                "create_submission",
                existing_count,
                cast(int | None, raw.get("analyzedAnswerCount")),
            )
        )
        original_create_submission(answer)

    monkeypatch.setattr(
        app.state.drill_repository,
        "initialize_analyzed_answer_count",
        record_initialize,
    )
    monkeypatch.setattr(
        app.state.answer_repository,
        "create_submission",
        record_create_submission,
    )
    observed_claim_state: list[tuple[int | None, int]] = []
    original_claim: Callable[[str], object] = (
        app.state.analysis_execution_repository.claim_auto_analysis
    )

    def record_claim_state(target_drill_run_id: str) -> object:
        raw = app.state.firestore_client.get_document(
            DrillRepository.collection,
            target_drill_run_id,
        )
        assert raw is not None
        observed_claim_state.append(
            (
                cast(int | None, raw.get("analyzedAnswerCount")),
                len(app.state.answer_repository.list_by_drill_run(target_drill_run_id)),
            )
        )
        return original_claim(target_drill_run_id)

    monkeypatch.setattr(
        app.state.analysis_execution_repository,
        "claim_auto_analysis",
        record_claim_state,
    )
    assert _course_needs_analysis(client, course_id) is False

    response = client.post(
        path,
        json={
            "learnerName": "新規受講者",
            "answers": [
                {"questionId": f"q{index}", "answerText": "短い回答"}
                for index in range(1, 4)
            ],
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "graded"
    assert persistence_events == [
        ("initialize_complete", 4, 4),
        ("create_submission", 4, 4),
    ]
    assert observed_claim_state == [(4, 5)]
    raw_after = app.state.firestore_client.get_document(
        DrillRepository.collection,
        drill_run_id,
    )
    model_after = app.state.drill_repository.get(drill_run_id)
    assert raw_after is not None
    assert raw_after["analyzedAnswerCount"] == 4
    assert "autoAnalyzedScoredAnswerCount" not in raw_after
    assert model_after is not None
    assert model_after.analyzed_answer_count == 4
    assert model_after.auto_analyzed_scored_answer_count is None
    assert model_after.status is DrillRunStatus.ANALYZED
    assert len(app.state.answer_repository.list_by_drill_run(drill_run_id)) == 5
    assert app.state.analysis_execution_repository.claim_auto_analysis(drill_run_id) is None
    assert _course_needs_analysis(client, course_id) is True


def test_rollout_reads_and_patch_resolution_do_not_trigger_auto_analysis(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, course_id, drill_run_id = _seed_legacy_drill(
        client,
        status=DrillRunStatus.READY,
        analyzed_answer_count=None,
        answer_count=5,
    )
    app.state.patch_repository.create(
        DocumentPatch(
            id="legacy-patch",
            course_id=course_id,
            drill_run_id=drill_run_id,
            status=PatchStatus.PROPOSED,
            base_markdown="# Body",
            patched_markdown="# Improved",
            patch_summary="改善",
            diff_text="-# Body\n+# Improved",
        )
    )
    claim_calls: list[str] = []

    def record_unexpected_claim(target_drill_run_id: str) -> None:
        claim_calls.append(target_drill_run_id)

    monkeypatch.setattr(
        app.state.analysis_execution_repository,
        "claim_auto_analysis",
        record_unexpected_claim,
    )

    raw_before_reads = app.state.firestore_client.get_document(
        DrillRepository.collection,
        drill_run_id,
    )
    assert raw_before_reads is not None
    assert "analyzedAnswerCount" not in raw_before_reads
    assert "autoAnalyzedScoredAnswerCount" not in raw_before_reads
    assert client.get("/api/courses").status_code == 200
    assert (
        app.state.firestore_client.get_document(DrillRepository.collection, drill_run_id)
        == raw_before_reads
    )
    assert client.get(f"/api/drill-runs/{drill_run_id}").status_code == 200
    assert (
        app.state.firestore_client.get_document(DrillRepository.collection, drill_run_id)
        == raw_before_reads
    )
    assert client.get("/api/patches/legacy-patch").status_code == 200
    assert (
        app.state.firestore_client.get_document(DrillRepository.collection, drill_run_id)
        == raw_before_reads
    )
    reject = client.post(
        "/api/patches/legacy-patch/reject",
        json={"ownerFeedback": "今回は見送ります"},
    )

    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"
    assert claim_calls == []
    raw_after_reject = app.state.firestore_client.get_document(
        DrillRepository.collection,
        drill_run_id,
    )
    assert raw_after_reject == raw_before_reads
    assert raw_after_reject is not None
    assert "analyzedAnswerCount" not in raw_after_reject
    assert "autoAnalyzedScoredAnswerCount" not in raw_after_reject
    saved_drill = app.state.drill_repository.get(drill_run_id)
    assert saved_drill is not None
    assert saved_drill.status is DrillRunStatus.READY
