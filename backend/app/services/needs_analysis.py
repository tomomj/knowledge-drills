from app.analysis_policy import compute_needs_analysis
from app.repositories.repositories import AnswerRepository, DrillRepository
from app.schemas import Course


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
