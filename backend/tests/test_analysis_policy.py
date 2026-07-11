import pytest

from app.analysis_policy import is_scored_answer, resolve_auto_analysis_watermark
from app.schemas import AnswerStatus, AnswerSubmission, DrillRun, DrillRunStatus


def _answer(
    *,
    status: AnswerStatus = AnswerStatus.GRADED,
    total_score: int | None = 1,
    max_score: int | None = 4,
) -> AnswerSubmission:
    return AnswerSubmission(
        id="answer-1",
        drill_run_id="drill-1",
        learner_name="Learner",
        status=status,
        answers={},
        total_score=total_score,
        max_score=max_score,
    )


def _drill_run(
    *,
    status: DrillRunStatus = DrillRunStatus.READY,
    analyzed_answer_count: int | None = None,
    auto_analyzed_scored_answer_count: int | None = None,
) -> DrillRun:
    return DrillRun(
        id="drill-1",
        course_id="course-1",
        status=status,
        analyzed_answer_count=analyzed_answer_count,
        auto_analyzed_scored_answer_count=auto_analyzed_scored_answer_count,
    )


@pytest.mark.parametrize("total_score", [0, 1])
def test_is_scored_answer_accepts_graded_answers_with_final_positive_max_score(
    total_score: int,
) -> None:
    assert is_scored_answer(_answer(total_score=total_score)) is True


@pytest.mark.parametrize(
    "answer",
    [
        _answer(status=AnswerStatus.GRADING),
        _answer(status=AnswerStatus.FAILED),
        _answer(total_score=None),
        _answer(max_score=None),
        _answer(max_score=0),
        _answer(max_score=-1),
    ],
    ids=[
        "grading",
        "failed",
        "missing-total",
        "missing-max",
        "zero-max",
        "negative-max",
    ],
)
def test_is_scored_answer_rejects_non_final_scores(answer: AnswerSubmission) -> None:
    assert is_scored_answer(answer) is False


@pytest.mark.parametrize("status", list(DrillRunStatus))
def test_resolver_prefers_dedicated_watermark_regardless_of_status(
    status: DrillRunStatus,
) -> None:
    drill_run = _drill_run(
        status=status,
        analyzed_answer_count=3,
        auto_analyzed_scored_answer_count=7,
    )

    assert resolve_auto_analysis_watermark(drill_run, 5) == 7


@pytest.mark.parametrize(
    ("legacy_count", "current_scored_count", "expected"),
    [(3, 5, 3), (7, 5, 5)],
)
@pytest.mark.parametrize("status", list(DrillRunStatus))
def test_resolver_caps_legacy_fallback_at_current_scored_count(
    status: DrillRunStatus,
    legacy_count: int,
    current_scored_count: int,
    expected: int,
) -> None:
    drill_run = _drill_run(status=status, analyzed_answer_count=legacy_count)

    assert resolve_auto_analysis_watermark(drill_run, current_scored_count) == expected


@pytest.mark.parametrize("status", list(DrillRunStatus))
def test_resolver_returns_unknown_without_either_watermark_regardless_of_status(
    status: DrillRunStatus,
) -> None:
    drill_run = _drill_run(status=status)

    assert resolve_auto_analysis_watermark(drill_run, 5) is None
