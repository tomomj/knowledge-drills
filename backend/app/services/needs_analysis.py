from collections.abc import Mapping, Sequence
from fractions import Fraction

from app.repositories.repositories import AnswerRepository, DrillRepository
from app.schemas import (
    AnswerStatus,
    AnswerSubmission,
    Course,
    DrillRun,
    DrillRunStatus,
)

NEEDS_ANALYSIS_MIN_UNANALYZED: int = 1
NEEDS_ANALYSIS_SCORE_RATE_THRESHOLD: float = 0.7


def _score_rate(answer: AnswerSubmission) -> Fraction | None:
    if (
        answer.status is not AnswerStatus.GRADED
        or answer.total_score is None
        or answer.max_score is None
        or answer.max_score <= 0
    ):
        return None
    return Fraction(answer.total_score, answer.max_score)


def compute_needs_analysis(
    course_version: int,
    drill_runs: Sequence[DrillRun],
    answers_by_run: Mapping[str, Sequence[AnswerSubmission]],
) -> bool:
    """Return whether the current course version needs answer analysis."""
    score_rates: list[Fraction] = []
    unanalyzed_count = 0

    for drill_run in drill_runs:
        if drill_run.course_version != course_version:
            continue

        valid_score_rates = [
            score_rate
            for answer in answers_by_run.get(drill_run.id, ())
            if (score_rate := _score_rate(answer)) is not None
        ]
        score_rates.extend(valid_score_rates)

        if drill_run.status is DrillRunStatus.READY:
            unanalyzed_count += len(valid_score_rates)
        elif (
            drill_run.status is DrillRunStatus.ANALYZED
            and drill_run.analyzed_answer_count is not None
        ):
            unanalyzed_count += max(
                0,
                len(valid_score_rates) - drill_run.analyzed_answer_count,
            )

    if not score_rates:
        return False

    average_score_rate = sum(score_rates, start=Fraction()) / len(score_rates)
    return (
        unanalyzed_count >= NEEDS_ANALYSIS_MIN_UNANALYZED
        and average_score_rate < Fraction(str(NEEDS_ANALYSIS_SCORE_RATE_THRESHOLD))
    )


def evaluate_course_needs_analysis(
    course: Course,
    drill_repository: DrillRepository,
    answer_repository: AnswerRepository,
) -> bool:
    """Read current drill data and evaluate whether the course needs analysis."""
    current_drill_runs = [
        drill_run
        for drill_run in drill_repository.list_by_course(course.id)
        if drill_run.course_version == course.version
    ]
    answers_by_run = {
        drill_run.id: answer_repository.list_by_drill_run(drill_run.id)
        for drill_run in current_drill_runs
    }
    return compute_needs_analysis(course.version, current_drill_runs, answers_by_run)
