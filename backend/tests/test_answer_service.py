from typing import cast

import pytest

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.errors import AppError
from app.repositories.firestore_client import InMemoryFirestoreClient
from app.repositories.repositories import AnswerRepository, DrillRepository, ShareTokenRepository
from app.schemas import (
    AnswerInput,
    DrillQuestion,
    DrillRun,
    DrillRunStatus,
    RubricItem,
    SourceEvidence,
    SubmitAnswerRequest,
)
from app.services.answer_service import AnswerService


def _drill_run() -> DrillRun:
    questions = [
        DrillQuestion(
            id=f"q{index}",
            question="判断理由を書いてください。",
            intent="判断を見る",
            rubric=[RubricItem(criterion="根拠", points=4)],
            ideal_answer="根拠に基づき判断する。",
            source_evidence=[SourceEvidence(section_heading="方針", excerpt="## 方針")],
            max_score=4,
        )
        for index in range(1, 4)
    ]
    return DrillRun(
        id="drill-1",
        course_id="course-1",
        status=DrillRunStatus.READY,
        questions=questions,
    )


def _request(
    *,
    learner_name: str = "受講者",
    answers: list[AnswerInput] | None = None,
) -> SubmitAnswerRequest:
    return SubmitAnswerRequest(
        learner_name=learner_name,
        answers=answers
        or [
            AnswerInput(question_id="q1", answer_text="回答1"),
            AnswerInput(question_id="q2", answer_text="回答2"),
            AnswerInput(question_id="q3", answer_text="回答3"),
        ],
    )


def test_submit_answer_validation_accepts_matching_three_answers() -> None:
    service = AnswerService()

    validated = service.validate_submission(_drill_run(), _request())

    assert validated == {"q1": "回答1", "q2": "回答2", "q3": "回答3"}


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (_request(learner_name=""), "learner_name_required"),
        (
            _request(
                answers=[
                    AnswerInput(question_id="q1", answer_text=""),
                    AnswerInput(question_id="q2", answer_text="回答2"),
                    AnswerInput(question_id="q3", answer_text="回答3"),
                ]
            ),
            "answer_text_required",
        ),
        (
            _request(
                answers=[
                    AnswerInput(question_id="q1", answer_text="回答1"),
                    AnswerInput(question_id="q2", answer_text="回答2"),
                ]
            ),
            "answer_count_invalid",
        ),
        (
            _request(
                answers=[
                    AnswerInput(question_id="q1", answer_text="回答1"),
                    AnswerInput(question_id="q2", answer_text="回答2"),
                    AnswerInput(question_id="q4", answer_text="回答4"),
                ]
            ),
            "answer_question_mismatch",
        ),
        (
            _request(
                answers=[
                    AnswerInput(question_id="q1", answer_text="回答1"),
                    AnswerInput(question_id="q1", answer_text="回答1"),
                    AnswerInput(question_id="q2", answer_text="回答2"),
                ]
            ),
            "answer_question_duplicate",
        ),
    ],
)
def test_submit_answer_validation_rejects_invalid_request(
    payload: SubmitAnswerRequest,
    code: str,
) -> None:
    service = AnswerService()

    with pytest.raises(AppError) as exc_info:
        service.validate_submission(_drill_run(), payload)

    assert exc_info.value.code == code


def _configured_service(
    agent_response: dict[str, object],
) -> tuple[AnswerService, AnswerRepository]:
    client = InMemoryFirestoreClient()
    drill_repository = DrillRepository(client)
    answer_repository = AnswerRepository(client)
    token_repository = ShareTokenRepository(client)
    drill_repository.create(_drill_run())
    token_repository.reserve("share-token", drill_run_id="drill-1")
    service = AnswerService(
        drill_repository=drill_repository,
        answer_repository=answer_repository,
        share_token_repository=token_repository,
        agent_client=AgentRuntimeClient(
            invoker=lambda _task_name, payload: _agent_response_for_question(
                agent_response,
                payload,
            )
        ),
    )
    return service, answer_repository


def _agent_response_for_question(
    agent_response: dict[str, object],
    payload: dict[str, object],
) -> dict[str, object]:
    if "questionId" not in agent_response:
        return agent_response
    question = cast(dict[str, object], payload["question"])
    return {**agent_response, "questionId": question["id"]}


def test_submit_answer_grades_and_persists_results() -> None:
    service, answer_repository = _configured_service(
        {
            "questionId": "q1",
            "score": 4,
            "maxScore": 4,
            "correctPoints": ["根拠がある"],
            "missingPoints": [],
            "feedback": "よい回答です。",
            "failureTags": [],
        }
    )

    answer = service.submit_answer("share-token", _request())

    saved = answer_repository.get(answer.id)
    assert saved is not None
    assert saved.status == "graded"
    assert saved.total_score == 12
    assert saved.max_score == 12
    assert len(saved.grading_results) == 3


def test_submit_answer_marks_failed_when_grading_fails() -> None:
    service, answer_repository = _configured_service({"invalid": "payload"})

    with pytest.raises(Exception, match="schema validation failed"):
        service.submit_answer("share-token", _request())

    saved_answers = answer_repository.list_by_drill_run("drill-1")
    assert len(saved_answers) == 1
    assert saved_answers[0].status == "failed"
    assert saved_answers[0].error_message == "grading failed"
