from typing import cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.schemas import Course, DocumentPatch, FailureSeverity, FailureSignal, PatchStatus


def _patch(status: PatchStatus = PatchStatus.PROPOSED) -> DocumentPatch:
    return DocumentPatch(
        id="patch-1",
        course_id="course-1",
        drill_run_id="drill-1",
        status=status,
        base_markdown="# Before",
        patched_markdown="# After",
        patch_summary="判断基準を追記",
        risk_notes=["既存運用との整合を確認"],
        diff_text="--- base.md\n+++ patched.md\n-# Before\n+# After",
        failure_signals=[
            FailureSignal(
                id="fs_test_001",
                title="根拠不足",
                severity=FailureSeverity.MEDIUM,
                evidence=["q1 で根拠不足が多い"],
                likely_cause="判断基準の記載が薄い",
                suspected_document_gap="例外条件が不足",
                target_sections=["## 判断基準"],
                recommended_change="例外条件を追記",
                sample_size=2,
                confidence_note="少数回答の傾向です。",
            )
        ],
    )


def _seed_patch(client: TestClient, status: PatchStatus = PatchStatus.PROPOSED) -> None:
    app = cast(FastAPI, client.app)
    app.state.course_repository.create(
        Course(id="course-1", owner_user_id="local-owner", title="講座", markdown="# Before")
    )
    app.state.patch_repository.create(_patch(status=status))


def test_get_patch_returns_patch_detail(client: TestClient) -> None:
    _seed_patch(client)

    response = client.get("/api/patches/patch-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "proposed"
    assert payload["patchSummary"] == "判断基準を追記"
    assert payload["failureSignals"][0]["sampleSize"] == 2
    assert payload["failureSignals"][0]["confidenceNote"] == "少数回答の傾向です。"


def test_get_patch_marks_stale_when_course_changed(client: TestClient) -> None:
    _seed_patch(client)
    app = cast(FastAPI, client.app)
    app.state.course_repository.update(
        Course(id="course-1", owner_user_id="local-owner", title="講座", markdown="# Changed")
    )

    response = client.get("/api/patches/patch-1")

    assert response.status_code == 200
    assert response.json()["status"] == "stale"


def test_apply_patch_updates_course_and_saves_feedback(client: TestClient) -> None:
    _seed_patch(client)

    response = client.post("/api/patches/patch-1/apply", json={"ownerFeedback": "反映します"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "applied"
    assert payload["ownerFeedback"] == "反映します"
    app = cast(FastAPI, client.app)
    course = app.state.course_repository.get("course-1")
    assert course is not None
    assert course.markdown == "# After"
    assert course.version == 2


def test_reject_patch_saves_feedback_without_updating_course(client: TestClient) -> None:
    _seed_patch(client)

    response = client.post("/api/patches/patch-1/reject", json={"ownerFeedback": "不要です"})

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    app = cast(FastAPI, client.app)
    course = app.state.course_repository.get("course-1")
    assert course is not None
    assert course.markdown == "# Before"


def test_patch_decision_conflict_returns_current_status(client: TestClient) -> None:
    _seed_patch(client, status=PatchStatus.APPLIED)

    response = client.post("/api/patches/patch-1/reject", json={"ownerFeedback": "遅い"})

    assert response.status_code == 409
    assert response.json()["code"] == "patch_not_proposed"
    assert response.json()["currentStatus"] == "applied"
