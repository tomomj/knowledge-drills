import inspect

from app.routes.courses import analyze_course_drill, generate_drill
from app.routes.drills import analyze_drill
from app.routes.learn import submit_answer, submit_answer_legacy


def test_agent_reaching_routes_are_sync_functions() -> None:
    routes = [
        generate_drill,
        analyze_course_drill,
        analyze_drill,
        submit_answer,
        submit_answer_legacy,
    ]

    assert all(not inspect.iscoroutinefunction(route) for route in routes)


def test_legacy_submit_answer_delegates_without_await() -> None:
    source = inspect.getsource(submit_answer_legacy)

    assert "await submit_answer" not in source
