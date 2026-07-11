from collections.abc import Mapping, Sequence
from fractions import Fraction

from app.schemas import AnswerStatus, AnswerSubmission, DrillRun, DrillRunStatus

AUTO_ANALYSIS_MIN_ANSWERS: int = 5
NEEDS_ANALYSIS_MIN_UNANALYZED: int = 1
NEEDS_ANALYSIS_SCORE_RATE_THRESHOLD: float = 0.7


def is_scored_answer(answer: AnswerSubmission) -> bool:
    """Return whether an answer belongs to the auto-analysis scored population."""
    return (
        answer.status is AnswerStatus.GRADED
        and answer.total_score is not None
        and answer.max_score is not None
        and answer.max_score > 0
    )


def resolve_auto_analysis_watermark(
    drill_run: DrillRun,
    current_scored_answer_count: int,
) -> int | None:
    """Resolve a comparable scored-answer baseline without interpreting run status."""
    if drill_run.auto_analyzed_scored_answer_count is not None:
        return drill_run.auto_analyzed_scored_answer_count
    if drill_run.analyzed_answer_count is not None:
        return min(drill_run.analyzed_answer_count, current_scored_answer_count)
    return None


def count_unanalyzed_answers(
    drill_run: DrillRun,
    answers: Sequence[AnswerSubmission],
) -> int:
    """Count scored answers not covered by the effective analysis watermark."""
    current_scored_answer_count = sum(is_scored_answer(answer) for answer in answers)
    if drill_run.status is DrillRunStatus.READY:
        baseline = resolve_auto_analysis_watermark(
            drill_run,
            current_scored_answer_count,
        )
        if baseline is None:
            baseline = 0
    elif drill_run.status is DrillRunStatus.ANALYZED:
        baseline = resolve_auto_analysis_watermark(
            drill_run,
            current_scored_answer_count,
        )
        if baseline is None:
            return 0
    else:
        return 0
    return max(0, current_scored_answer_count - baseline)


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

        scored_answers = [
            answer
            for answer in answers_by_run.get(drill_run.id, ())
            if is_scored_answer(answer)
        ]
        score_rates.extend(
            Fraction(answer.total_score, answer.max_score)
            for answer in scored_answers
            if answer.total_score is not None and answer.max_score is not None
        )
        if (
            drill_run.status is DrillRunStatus.READY
            and drill_run.auto_analyzed_scored_answer_count is None
        ):
            # Preserve the legacy needs-analysis rule for READY runs. The legacy
            # count can survive a failed analysis, but READY historically treated
            # every scored answer as unanalyzed.
            unanalyzed_count += len(scored_answers)
        else:
            unanalyzed_count += count_unanalyzed_answers(drill_run, scored_answers)

    if not score_rates:
        return False

    average_score_rate = sum(score_rates, start=Fraction()) / len(score_rates)
    return (
        unanalyzed_count >= NEEDS_ANALYSIS_MIN_UNANALYZED
        and average_score_rate < Fraction(str(NEEDS_ANALYSIS_SCORE_RATE_THRESHOLD))
    )
