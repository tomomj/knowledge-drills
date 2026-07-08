import pytest

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import CourseRepository, DrillRepository, ShareTokenRepository
from app.schemas import Course
from app.services.drill_service import DrillService
from app.services.share_token_service import ShareTokenService


def _question_payload(
    question_id: str = "q1",
    points: int = 4,
    excerpt: str = "## 方針",
) -> dict[str, object]:
    return {
        "id": question_id,
        "scenario": "判断理由を書いてください。",
        "intent": "実務判断を見る。",
        "rubric": [{"criterion": "根拠", "points": points}],
        "idealAnswer": "根拠に基づき判断する。",
        "sourceEvidence": [{"sectionHeading": "方針", "excerpt": excerpt}],
        "maxScore": 4,
    }


def _service(
    agent_response: dict[str, object],
    *,
    course: Course | None = None,
    observed_payloads: list[dict[str, object]] | None = None,
) -> tuple[DrillService, CourseRepository, DrillRepository]:
    client = InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    drill_repository = DrillRepository(client)
    token_repository = ShareTokenRepository(client)
    course_repository.create(
        course
        or Course(
            id="course-1",
            owner_user_id="owner-1",
            title="講座",
            markdown="# Body\n\n## 方針\n根拠を確認します。",
        )
    )

    def invoke(_task_name: str, payload: dict[str, object]) -> dict[str, object]:
        if observed_payloads is not None:
            observed_payloads.append(payload)
        return agent_response

    service = DrillService(
        course_repository=course_repository,
        drill_repository=drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=drill_repository,
            share_token_repository=token_repository,
            token_generator=lambda: "share-token",
        ),
        agent_client=AgentRuntimeClient(invoker=invoke),
    )
    return service, course_repository, drill_repository


def test_generate_drill_marks_run_ready_with_three_valid_questions() -> None:
    service, course_repository, drill_repository = _service(
        {
            "questions": [
                _question_payload("q1"),
                _question_payload("q2"),
                _question_payload("q3"),
            ]
        }
    )

    drill_run = service.generate_drill("course-1", "owner-1")

    saved = drill_repository.get(drill_run.id)
    assert saved is not None
    assert saved.status == "ready"
    assert saved.share_token == "share-token"
    assert len(saved.questions) == 3
    course = course_repository.get("course-1")
    assert course is not None
    assert course.latest_drill_run_id == drill_run.id
    assert course.latest_drill_status == "ready"
    assert course.answer_count == 0


def test_generate_drill_snapshots_drill_focus_and_sends_it_to_agent() -> None:
    observed_payloads: list[dict[str, object]] = []
    service, course_repository, drill_repository = _service(
        {
            "questions": [
                _question_payload("q1"),
                _question_payload("q2"),
                _question_payload("q3"),
            ]
        },
        course=Course(
            id="course-1",
            owner_user_id="owner-1",
            title="講座",
            markdown="# Body\n\n## 方針\n根拠を確認します。",
            drill_focus="例外条件を重点的に出す",
        ),
        observed_payloads=observed_payloads,
    )

    drill_run = service.generate_drill("course-1", "owner-1")

    assert observed_payloads[0]["drillFocus"] == "例外条件を重点的に出す"
    saved = drill_repository.get(drill_run.id)
    assert saved is not None
    assert saved.drill_focus == "例外条件を重点的に出す"

    course = course_repository.get("course-1")
    assert course is not None
    course_repository.update(
        course.model_copy(update={"drill_focus": "変更後の観点", "version": course.version + 1})
    )

    saved_after_course_update = drill_repository.get(drill_run.id)
    assert saved_after_course_update is not None
    assert saved_after_course_update.drill_focus == "例外条件を重点的に出す"


@pytest.mark.parametrize("excerpt", ["## 存在しない方針", "   "])
def test_generate_drill_marks_run_failed_when_source_evidence_is_not_in_course(
    excerpt: str,
) -> None:
    service, course_repository, drill_repository = _service(
        {
            "questions": [
                _question_payload("q1", excerpt=excerpt),
                _question_payload("q2"),
                _question_payload("q3"),
            ]
        }
    )

    drill_run = service.generate_drill("course-1", "owner-1")

    saved_runs = drill_repository.list_by_course("course-1")
    assert drill_run.id == saved_runs[0].id
    assert drill_run.status == "failed"
    assert saved_runs[0].status == "failed"
    assert saved_runs[0].questions == []
    assert saved_runs[0].error_message == "drill generation failed"
    course = course_repository.get("course-1")
    assert course is not None
    assert course.latest_drill_status == "failed"


def test_generate_drill_marks_run_failed_when_agent_output_is_invalid() -> None:
    service, course_repository, drill_repository = _service(
        {
            "questions": [
                _question_payload("q1", points=3),
                _question_payload("q2"),
                _question_payload("q3"),
            ]
        }
    )

    drill_run = service.generate_drill("course-1", "owner-1")

    saved_runs = drill_repository.list_by_course("course-1")
    assert drill_run.id == saved_runs[0].id
    assert drill_run.status == "failed"
    assert saved_runs[0].status == "failed"
    assert saved_runs[0].error_message == "drill generation failed"
    course = course_repository.get("course-1")
    assert course is not None
    assert course.latest_drill_run_id == saved_runs[0].id
    assert course.latest_drill_status == "failed"


def test_generate_drill_rejects_missing_course() -> None:
    service, _course_repository, _drill_repository = _service(
        {
            "questions": [
                _question_payload("q1"),
                _question_payload("q2"),
                _question_payload("q3"),
            ]
        }
    )

    with pytest.raises(Exception, match="Course was not found"):
        service.generate_drill("missing-course", "owner-1")
