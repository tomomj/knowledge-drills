from typing import cast

import pytest

from app.repositories.repositories import AnalysisExecutionRepository
from app.schemas import AnalysisClaim, AnalysisOrigin, DocumentPatch
from app.services.analysis_service import AnalysisService
from app.services.auto_analysis import AutoAnalysisTrigger


class FakeLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def info(self, message: str, *args: object) -> None:
        self.records.append(("info", message % args))

    def warning(self, message: str, *args: object) -> None:
        self.records.append(("warning", message % args))


class StubExecutionRepository:
    def __init__(
        self,
        claim_result: AnalysisClaim | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.claim_result = claim_result
        self.error = error
        self.claimed_drill_run_ids: list[str] = []

    def claim_auto_analysis(self, drill_run_id: str) -> AnalysisClaim | None:
        self.claimed_drill_run_ids.append(drill_run_id)
        if self.error is not None:
            raise self.error
        return self.claim_result


class StubAnalysisService:
    def __init__(
        self,
        result: DocumentPatch | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.claims: list[AnalysisClaim] = []

    def run_claimed_analysis(self, claim: AnalysisClaim) -> DocumentPatch | None:
        self.claims.append(claim)
        if self.error is not None:
            raise self.error
        return self.result


def make_claim() -> AnalysisClaim:
    return AnalysisClaim(
        course_id="course-safe",
        drill_run_id="drill-safe",
        owner_user_id="owner-safe",
        course_version=3,
        answer_ids=("answer-secret-a", "answer-secret-b"),
        snapshot_agent_answer_count=2,
        snapshot_scored_answer_count=2,
        origin=AnalysisOrigin.AUTOMATIC,
    )


def make_trigger(
    monkeypatch: pytest.MonkeyPatch,
    repository: StubExecutionRepository,
    service: StubAnalysisService,
) -> tuple[AutoAnalysisTrigger, FakeLogger]:
    fake_logger = FakeLogger()
    monkeypatch.setattr("app.services.auto_analysis.logger", fake_logger)
    return (
        AutoAnalysisTrigger(
            cast(AnalysisExecutionRepository, repository),
            cast(AnalysisService, service),
        ),
        fake_logger,
    )


def test_maybe_run_logs_skipped_and_does_not_execute_without_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = StubExecutionRepository()
    service = StubAnalysisService()
    trigger, fake_logger = make_trigger(monkeypatch, repository, service)

    trigger.maybe_run("drill-safe")

    assert repository.claimed_drill_run_ids == ["drill-safe"]
    assert service.claims == []
    assert fake_logger.records == [
        (
            "info",
            "auto_analysis_skipped drill_run_id=drill-safe reason=claim_not_acquired",
        )
    ]


def test_maybe_run_logs_started_and_completed_and_executes_claim_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = make_claim()
    repository = StubExecutionRepository(claim)
    service = StubAnalysisService()
    trigger, fake_logger = make_trigger(monkeypatch, repository, service)

    trigger.maybe_run("drill-safe")

    assert service.claims == [claim]
    assert fake_logger.records == [
        (
            "info",
            "auto_analysis_started course_id=course-safe drill_run_id=drill-safe "
            "origin=automatic snapshot_agent_answer_count=2 snapshot_scored_answer_count=2",
        ),
        (
            "info",
            "auto_analysis_completed course_id=course-safe drill_run_id=drill-safe "
            "origin=automatic snapshot_agent_answer_count=2 snapshot_scored_answer_count=2",
        ),
    ]


def test_maybe_run_logs_completed_when_executor_returns_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = make_claim()
    repository = StubExecutionRepository(claim)
    service = StubAnalysisService(result=cast(DocumentPatch, object()))
    trigger, fake_logger = make_trigger(monkeypatch, repository, service)

    trigger.maybe_run("drill-safe")

    assert service.claims == [claim]
    assert [message.split()[0] for _, message in fake_logger.records] == [
        "auto_analysis_started",
        "auto_analysis_completed",
    ]


def test_maybe_run_swallows_claim_exception_and_logs_only_safe_failure_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "credential=super-secret answer body"
    repository = StubExecutionRepository(error=RuntimeError(secret))
    service = StubAnalysisService()
    trigger, fake_logger = make_trigger(monkeypatch, repository, service)

    trigger.maybe_run("drill-safe")

    assert service.claims == []
    assert fake_logger.records == [
        (
            "warning",
            "auto_analysis_failed drill_run_id=drill-safe error_type=RuntimeError",
        )
    ]
    assert secret not in str(fake_logger.records)


def test_maybe_run_swallows_executor_exception_and_never_logs_sensitive_claim_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = make_claim()
    secret = "api_key=super-secret Failure Signal details"
    repository = StubExecutionRepository(claim)
    service = StubAnalysisService(error=RuntimeError(secret))
    trigger, fake_logger = make_trigger(monkeypatch, repository, service)

    trigger.maybe_run("drill-safe")

    assert service.claims == [claim]
    assert fake_logger.records[-1] == (
        "warning",
        "auto_analysis_failed course_id=course-safe drill_run_id=drill-safe "
        "origin=automatic snapshot_agent_answer_count=2 snapshot_scored_answer_count=2 "
        "error_type=RuntimeError",
    )
    rendered_logs = str(fake_logger.records)
    assert secret not in rendered_logs
    assert "answer-secret" not in rendered_logs
    assert "owner-safe" not in rendered_logs
