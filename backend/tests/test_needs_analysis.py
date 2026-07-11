from unittest.mock import call, create_autospec

import pytest

from app.repositories.repositories import AnswerRepository, DrillRepository
from app.schemas import AnswerStatus, AnswerSubmission, Course, DrillRun, DrillRunStatus
from app.services.needs_analysis import (
    NEEDS_ANALYSIS_MIN_UNANALYZED,
    NEEDS_ANALYSIS_SCORE_RATE_THRESHOLD,
    compute_needs_analysis,
    evaluate_course_needs_analysis,
)


def _drill_run(
    drill_run_id: str = "run-1",
    *,
    course_version: int = 1,
    status: DrillRunStatus = DrillRunStatus.READY,
    analyzed_answer_count: int | None = None,
) -> DrillRun:
    return DrillRun(
        id=drill_run_id,
        course_id="course-1",
        course_version=course_version,
        status=status,
        analyzed_answer_count=analyzed_answer_count,
    )


def _answer(
    answer_id: str,
    *,
    drill_run_id: str = "run-1",
    status: AnswerStatus = AnswerStatus.GRADED,
    total_score: int | None = 0,
    max_score: int | None = 100,
) -> AnswerSubmission:
    return AnswerSubmission(
        id=answer_id,
        drill_run_id=drill_run_id,
        learner_name="Learner",
        status=status,
        answers={},
        total_score=total_score,
        max_score=max_score,
    )


def _compute(
    answers: list[AnswerSubmission],
    *,
    drill_run: DrillRun | None = None,
) -> bool:
    run = drill_run or _drill_run()
    return compute_needs_analysis(1, [run], {run.id: answers})


def test_threshold_constants_are_centralized() -> None:
    assert NEEDS_ANALYSIS_MIN_UNANALYZED == 3
    assert NEEDS_ANALYSIS_SCORE_RATE_THRESHOLD == 0.7


def test_unanalyzed_answer_count_boundary_is_three() -> None:
    two_answers = [_answer("answer-1"), _answer("answer-2")]
    three_answers = [*two_answers, _answer("answer-3")]

    assert _compute(two_answers) is False
    assert _compute(three_answers) is True


def test_average_score_rate_must_be_strictly_below_seventy_percent() -> None:
    exactly_seventy = [_answer(f"answer-{index}", total_score=70) for index in range(3)]
    below_seventy = [_answer(f"answer-{index}", total_score=69) for index in range(3)]

    assert _compute(exactly_seventy) is False
    assert _compute(below_seventy) is True


def test_only_graded_answers_with_final_scores_are_included() -> None:
    answers = [
        _answer("graded-1"),
        _answer("graded-2"),
        _answer("graded-3"),
        _answer("grading", status=AnswerStatus.GRADING, total_score=100),
        _answer("failed", status=AnswerStatus.FAILED, total_score=100),
        _answer("missing-total", total_score=None),
        _answer("missing-max", max_score=None),
        _answer("zero-max", max_score=0),
    ]

    assert _compute(answers) is True


def test_non_graded_answers_do_not_count_toward_unanalyzed_threshold() -> None:
    answers = [
        _answer("graded-1"),
        _answer("graded-2"),
        _answer("grading-1", status=AnswerStatus.GRADING),
        _answer("grading-2", status=AnswerStatus.GRADING),
        _answer("failed-1", status=AnswerStatus.FAILED),
        _answer("failed-2", status=AnswerStatus.FAILED),
    ]

    assert _compute(answers) is False


def test_non_graded_answers_do_not_affect_average_score_rate() -> None:
    answers = [
        *[_answer(f"graded-{index}") for index in range(3)],
        *[
            _answer(f"grading-{index}", status=AnswerStatus.GRADING, total_score=100)
            for index in range(4)
        ],
        *[
            _answer(f"failed-{index}", status=AnswerStatus.FAILED, total_score=100)
            for index in range(4)
        ],
    ]

    assert _compute(answers) is True


def test_unscored_graded_answers_do_not_count_toward_threshold() -> None:
    answers = [
        _answer("graded-1"),
        _answer("graded-2"),
        _answer("missing-total", total_score=None),
        _answer("missing-max", max_score=None),
        _answer("zero-max", max_score=0),
    ]

    assert _compute(answers) is False


def test_average_uses_every_valid_graded_answer_including_analyzed_answers() -> None:
    ready = _drill_run("ready")
    analyzed = _drill_run(
        "analyzed",
        status=DrillRunStatus.ANALYZED,
        analyzed_answer_count=7,
    )
    answers_by_run = {
        ready.id: [_answer(f"low-{index}", drill_run_id=ready.id) for index in range(3)],
        analyzed.id: [
            _answer(f"high-{index}", drill_run_id=analyzed.id, total_score=100)
            for index in range(7)
        ],
    }

    assert compute_needs_analysis(1, [ready, analyzed], answers_by_run) is False


def test_average_is_mean_of_each_answer_rate_not_aggregate_points() -> None:
    answers = [
        _answer("zero", total_score=0, max_score=1),
        _answer("full-1", total_score=2, max_score=2),
        _answer("full-2", total_score=2, max_score=2),
    ]

    assert _compute(answers) is True


@pytest.mark.parametrize(
    ("status", "analyzed_answer_count", "expected"),
    [
        (DrillRunStatus.READY, None, True),
        (DrillRunStatus.ANALYZING, None, False),
        (DrillRunStatus.GENERATING, None, False),
        (DrillRunStatus.FAILED, None, False),
        (DrillRunStatus.ANALYZED, 1, True),
        (DrillRunStatus.ANALYZED, 5, False),
        (DrillRunStatus.ANALYZED, None, False),
    ],
)
def test_run_status_controls_unanalyzed_count(
    status: DrillRunStatus,
    analyzed_answer_count: int | None,
    expected: bool,
) -> None:
    run = _drill_run(status=status, analyzed_answer_count=analyzed_answer_count)
    answers = [_answer(f"answer-{index}") for index in range(4)]

    assert _compute(answers, drill_run=run) is expected


@pytest.mark.parametrize(
    "answers",
    [
        [],
        [_answer("grading", status=AnswerStatus.GRADING)],
        [_answer("missing-total", total_score=None)],
        [_answer("missing-max", max_score=None)],
        [_answer("zero-max", max_score=0)],
    ],
)
def test_no_valid_graded_score_returns_false(answers: list[AnswerSubmission]) -> None:
    assert _compute(answers) is False


def test_past_course_versions_do_not_affect_count_or_average() -> None:
    current = _drill_run("current", course_version=2)
    past = _drill_run("past", course_version=1)
    answers_by_run = {
        current.id: [
            _answer("current-1", drill_run_id=current.id),
            _answer("current-2", drill_run_id=current.id),
        ],
        past.id: [
            _answer(f"past-{index}", drill_run_id=past.id) for index in range(3)
        ],
    }

    assert compute_needs_analysis(2, [current, past], answers_by_run) is False


def test_evaluate_reads_only_current_version_answers_and_delegates() -> None:
    course = Course(id="course-1", title="Course", markdown="# Course", version=2)
    current = _drill_run("current", course_version=2)
    past = _drill_run("past", course_version=1)
    current_answers = [
        _answer(f"answer-{index}", drill_run_id=current.id) for index in range(3)
    ]
    drill_repository = create_autospec(DrillRepository, instance=True)
    answer_repository = create_autospec(AnswerRepository, instance=True)
    drill_repository.list_by_course.return_value = [past, current]
    answer_repository.list_by_drill_run.return_value = current_answers

    result = evaluate_course_needs_analysis(course, drill_repository, answer_repository)

    assert result is True
    drill_repository.list_by_course.assert_called_once_with(course.id)
    answer_repository.list_by_drill_run.assert_called_once_with(current.id)
    assert drill_repository.method_calls == [call.list_by_course(course.id)]
    assert answer_repository.method_calls == [call.list_by_drill_run(current.id)]
