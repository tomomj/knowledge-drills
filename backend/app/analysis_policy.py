from app.schemas import AnswerStatus, AnswerSubmission, DrillRun


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
