import logging

import pytest
from _pytest.logging import LogCaptureFixture

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
    section_heading: str = "方針",
) -> dict[str, object]:
    return {
        "id": question_id,
        "scenario": "判断理由を書いてください。",
        "intent": "実務判断を見る。",
        "rubric": [{"criterion": "根拠", "points": points}],
        "idealAnswer": "根拠に基づき判断する。",
        "sourceEvidence": [{"sectionHeading": section_heading, "excerpt": excerpt}],
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


def test_generate_drill_snapshots_course_title_and_markdown() -> None:
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
    assert saved.course_title == "講座"
    assert saved.course_markdown == "# Body\n\n## 方針\n根拠を確認します。"

    course = course_repository.get("course-1")
    assert course is not None
    course_repository.update(
        course.model_copy(
            update={
                "title": "更新後の講座",
                "markdown": "# 更新後の本文",
                "version": course.version + 1,
            }
        )
    )

    saved_after_course_update = drill_repository.get(drill_run.id)
    assert saved_after_course_update is not None
    assert saved_after_course_update.course_title == "講座"
    assert saved_after_course_update.course_markdown == "# Body\n\n## 方針\n根拠を確認します。"


def test_generate_drill_normalizes_heading_only_source_evidence() -> None:
    service, _course_repository, drill_repository = _service(
        {
            "questions": [
                _question_payload("q1", excerpt="方針"),
                _question_payload("q2", excerpt="方針"),
                _question_payload("q3", excerpt="方針"),
            ]
        }
    )

    drill_run = service.generate_drill("course-1", "owner-1")

    saved = drill_repository.get(drill_run.id)
    assert saved is not None
    assert saved.status == "ready"
    assert all(
        evidence.excerpt == "## 方針"
        for question in saved.questions
        for evidence in question.source_evidence
    )


def test_generate_drill_normalizes_source_evidence_across_markdown_whitespace() -> None:
    course_markdown = (
        "# 顧客情報の取り扱い\n\n"
        "## 本人確認\n\n"
        "契約内容、請求情報、登録メールアドレスなどの個人情報を案内する前に、"
        "本人確認を行う。本人確認では、登録氏名、登録メールアドレス、契約番号のうち"
        "二つ以上が一致していることを確認する。\n\n"
        "本人確認が完了しない場合は、個人情報を含む回答をしてはならない。"
        "その場合は、本人確認に必要な情報を案内し、確認完了後に改めて回答する。"
    )
    generated_excerpt = (
        "本人確認では、登録氏名、登録メールアドレス、契約番号のうち二つ以上が"
        "一致していることを確認する。本人確認が完了しない場合は、個人情報を含む"
        "回答をしてはならない。その場合は、本人確認に必要な情報を案内し、確認完了後に"
        "改めて回答する。"
    )
    service, _course_repository, drill_repository = _service(
        {
            "questions": [
                _question_payload("q1", excerpt=generated_excerpt),
                _question_payload("q2", excerpt="本人確認"),
                _question_payload("q3", excerpt="本人確認"),
            ]
        },
        course=Course(
            id="course-1",
            owner_user_id="owner-1",
            title="講座",
            markdown=course_markdown,
        ),
    )

    drill_run = service.generate_drill("course-1", "owner-1")

    saved = drill_repository.get(drill_run.id)
    assert saved is not None
    assert saved.status == "ready"
    normalized_excerpt = saved.questions[0].source_evidence[0].excerpt
    assert normalized_excerpt in course_markdown
    assert "\n\n" in normalized_excerpt


def test_generate_drill_falls_back_to_source_evidence_section_heading() -> None:
    service, _course_repository, drill_repository = _service(
        {
            "questions": [
                _question_payload(
                    "q1",
                    excerpt="教材にはない言い換えを含む根拠文です。",
                    section_heading="方針",
                ),
                _question_payload("q2"),
                _question_payload("q3"),
            ]
        }
    )

    drill_run = service.generate_drill("course-1", "owner-1")

    saved = drill_repository.get(drill_run.id)
    assert saved is not None
    assert saved.status == "ready"
    assert saved.questions[0].source_evidence[0].excerpt == "## 方針"


@pytest.mark.parametrize("excerpt", ["## 存在しない方針", "   "])
def test_generate_drill_marks_run_failed_when_source_evidence_is_not_in_course(
    excerpt: str,
) -> None:
    service, course_repository, drill_repository = _service(
        {
            "questions": [
                _question_payload("q1", excerpt=excerpt, section_heading="存在しない方針"),
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


def test_generate_drill_logs_validation_context_for_invalid_source_evidence(
    caplog: LogCaptureFixture,
) -> None:
    service, _course_repository, _drill_repository = _service(
        {
            "questions": [
                _question_payload(
                    "q1",
                    excerpt="## 存在しない方針",
                    section_heading="存在しない方針",
                ),
                _question_payload("q2"),
                _question_payload("q3"),
            ]
        }
    )

    with caplog.at_level(logging.WARNING, logger="app.drill"):
        drill_run = service.generate_drill("course-1", "owner-1")

    assert drill_run.status == "failed"
    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "drill generation validation failed course_id=course-1" in message
        and "question_id=q1" in message
        and "evidence_index=0" in message
        and "excerpt_preview=## 存在しない方針" in message
        for message in messages
    )


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
