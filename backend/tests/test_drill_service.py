import pytest

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import CourseRepository, DrillRepository, ShareTokenRepository
from app.schemas import Course
from app.services.drill_service import DrillService
from app.services.share_token_service import ShareTokenService


def _question_payload(question_id: str = "q1", points: int = 4) -> dict[str, object]:
    return {
        "id": question_id,
        "scenario": "判断理由を書いてください。",
        "intent": "実務判断を見る。",
        "rubric": [{"criterion": "根拠", "points": points}],
        "idealAnswer": "根拠に基づき判断する。",
        "sourceEvidence": ["## 方針"],
        "maxScore": 4,
    }


def _service(agent_response: dict[str, object]) -> tuple[DrillService, DrillRepository]:
    client = InMemoryFirestoreClient()
    course_repository = CourseRepository(client)
    drill_repository = DrillRepository(client)
    token_repository = ShareTokenRepository(client)
    course_repository.create(
        Course(id="course-1", owner_user_id="owner-1", title="講座", markdown="# Body")
    )
    service = DrillService(
        course_repository=course_repository,
        drill_repository=drill_repository,
        share_token_service=ShareTokenService(
            drill_repository=drill_repository,
            share_token_repository=token_repository,
            token_generator=lambda: "share-token",
        ),
        agent_client=AgentRuntimeClient(invoker=lambda _task_name, _payload: agent_response),
    )
    return service, drill_repository


def test_generate_drill_marks_run_ready_with_three_valid_questions() -> None:
    service, drill_repository = _service(
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


def test_generate_drill_marks_run_failed_when_agent_output_is_invalid() -> None:
    service, drill_repository = _service(
        {
            "questions": [
                _question_payload("q1", points=3),
                _question_payload("q2"),
                _question_payload("q3"),
            ]
        }
    )

    with pytest.raises(ValueError, match="rubric points"):
        service.generate_drill("course-1", "owner-1")

    saved_runs = drill_repository.list_by_course("course-1")
    assert saved_runs[0].status == "failed"
    assert saved_runs[0].error_message == "drill generation failed"


def test_generate_drill_rejects_missing_course() -> None:
    service, _drill_repository = _service(
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
