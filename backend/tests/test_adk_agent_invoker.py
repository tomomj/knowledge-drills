"""Unit tests for AdkAgentInvoker (task 2.2).

Fake Runners are injected via ``runner_factory``; no external generative AI
service, network access, or credentials are required.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Mapping
from typing import cast

import pytest
from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.clients.adk_agent_invoker import (
    AdkAgentConfigurationError,
    AdkAgentInvoker,
    _default_runner_factory,
    create_adk_invoker,
)
from app.clients.agent_runtime_client import AgentInvocationError
from app.config import Settings

TASK_NAMES = (
    "generate_drill",
    "grade_answer",
    "analyze_failures",
    "propose_document_patch",
)

TASK_TO_AGENT_NAME = {
    "generate_drill": "drill_generator_agent",
    "grade_answer": "grading_agent",
    "analyze_failures": "failure_analysis_agent",
    "propose_document_patch": "document_patch_agent",
}


class FakeSessionService:
    """Records session creation requests made by the invoker."""

    def __init__(self) -> None:
        self.created: list[dict[str, str]] = []

    async def create_session(
        self, *, app_name: str, user_id: str, session_id: str
    ) -> dict[str, str]:
        record = {"app_name": app_name, "user_id": user_id, "session_id": session_id}
        self.created.append(record)
        return record


class FakeRunner:
    """Stand-in for google.adk.runners.Runner recording run_async invocations."""

    def __init__(self, name: str, response_text: str, session_service: FakeSessionService) -> None:
        self.app_name = "fake-app"
        self.name = name
        self.response_text = response_text
        self.session_service = session_service
        self.calls: list[dict[str, object]] = []

    async def run_async(
        self, *, user_id: str, session_id: str, new_message: types.Content
    ) -> AsyncGenerator[Event, None]:
        self.calls.append(
            {"user_id": user_id, "session_id": session_id, "new_message": new_message}
        )
        # A partial (non-final) event first: the invoker must skip it.
        yield Event(
            author=self.name,
            partial=True,
            content=types.Content(role="model", parts=[types.Part(text="…thinking")]),
        )
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=self.response_text)]),
        )


class FakeNoFinalRunner:
    """Yields only non-final events."""

    app_name = "fake-app"

    def __init__(self, session_service: FakeSessionService) -> None:
        self.session_service = session_service

    async def run_async(
        self, *, user_id: str, session_id: str, new_message: types.Content
    ) -> AsyncGenerator[Event, None]:
        yield Event(
            author="no_final_agent",
            partial=True,
            content=types.Content(role="model", parts=[types.Part(text="partial")]),
        )


class FakeSlowRunner:
    """Never responds within the test timeout."""

    app_name = "fake-app"

    def __init__(self, session_service: FakeSessionService) -> None:
        self.session_service = session_service

    async def run_async(
        self, *, user_id: str, session_id: str, new_message: types.Content
    ) -> AsyncGenerator[Event, None]:
        await asyncio.sleep(1)
        yield Event(
            author="slow_agent",
            content=types.Content(role="model", parts=[types.Part(text='{"ok": true}')]),
        )


class FakeFailingRunner:
    """Raises from the ADK execution path."""

    app_name = "fake-app"

    def __init__(self, session_service: FakeSessionService, exc: Exception) -> None:
        self.session_service = session_service
        self.exc = exc

    async def run_async(
        self, *, user_id: str, session_id: str, new_message: types.Content
    ) -> AsyncGenerator[Event, None]:
        raise self.exc
        yield Event(author="unreachable")


class FakeRunnerHarness:
    """Bundles the fake runners with a counting runner factory."""

    def __init__(self) -> None:
        self.session_service = FakeSessionService()
        self.runners: dict[str, FakeRunner] = {
            task_name: FakeRunner(
                name=TASK_TO_AGENT_NAME[task_name],
                response_text=json.dumps({"agent": TASK_TO_AGENT_NAME[task_name]}),
                session_service=self.session_service,
            )
            for task_name in TASK_NAMES
        }
        self.factory_calls = 0

    def factory(self) -> Mapping[str, Runner]:
        self.factory_calls += 1
        return cast(Mapping[str, Runner], self.runners)


@pytest.fixture
def harness() -> FakeRunnerHarness:
    return FakeRunnerHarness()


def _make_invoker(harness: FakeRunnerHarness) -> AdkAgentInvoker:
    return AdkAgentInvoker(timeout_seconds=5.0, runner_factory=harness.factory)


def _make_single_runner_invoker(runner: object, *, timeout_seconds: float = 5.0) -> AdkAgentInvoker:
    return AdkAgentInvoker(
        timeout_seconds=timeout_seconds,
        runner_factory=lambda: {"generate_drill": cast(Runner, runner)},
    )


def _clear_google_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
    ):
        monkeypatch.delenv(name, raising=False)


def test_all_four_task_names_map_to_their_runner_and_return_response_dict(
    harness: FakeRunnerHarness,
) -> None:
    invoker = _make_invoker(harness)

    for task_name in TASK_NAMES:
        response = invoker(task_name, {"probe": task_name})
        assert response == {"agent": TASK_TO_AGENT_NAME[task_name]}

    for task_name in TASK_NAMES:
        assert len(harness.runners[task_name].calls) == 1, task_name


def test_payload_is_sent_as_json_string_user_message(harness: FakeRunnerHarness) -> None:
    invoker = _make_invoker(harness)
    payload: dict[str, object] = {"courseTitle": "講座", "courseMarkdown": "# 講座\n本文"}

    invoker("generate_drill", payload)

    calls = harness.runners["generate_drill"].calls
    assert len(calls) == 1
    message = cast(types.Content, calls[0]["new_message"])
    assert message.role == "user"
    assert message.parts is not None and len(message.parts) == 1
    text = message.parts[0].text
    assert text is not None
    assert json.loads(text) == payload


def test_unknown_task_name_raises_agent_invocation_error(harness: FakeRunnerHarness) -> None:
    invoker = _make_invoker(harness)

    with pytest.raises(AgentInvocationError):
        invoker("improve_course", {"probe": "x"})

    for runner in harness.runners.values():
        assert runner.calls == []


def test_runners_are_built_once_at_construction_and_reused(harness: FakeRunnerHarness) -> None:
    invoker = _make_invoker(harness)
    assert harness.factory_calls == 1

    invoker("grade_answer", {"probe": "1"})
    invoker("grade_answer", {"probe": "2"})
    invoker("analyze_failures", {"probe": "3"})

    assert harness.factory_calls == 1
    assert len(harness.runners["grade_answer"].calls) == 2
    assert len(harness.runners["analyze_failures"].calls) == 1


def test_each_call_runs_in_a_new_session(harness: FakeRunnerHarness) -> None:
    invoker = _make_invoker(harness)

    invoker("grade_answer", {"probe": "1"})
    invoker("grade_answer", {"probe": "2"})

    created = harness.session_service.created
    assert len(created) == 2
    assert created[0]["session_id"] != created[1]["session_id"]
    assert all(record["app_name"] == "fake-app" for record in created)

    run_session_ids = [call["session_id"] for call in harness.runners["grade_answer"].calls]
    assert run_session_ids == [record["session_id"] for record in created]


def test_logs_task_name_but_never_payload_contents(
    harness: FakeRunnerHarness, caplog: pytest.LogCaptureFixture
) -> None:
    invoker = _make_invoker(harness)
    sentinel = "SECRET_COURSE_BODY_78b5"

    with caplog.at_level(logging.DEBUG, logger="app.agent"):
        invoker("generate_drill", {"courseMarkdown": sentinel})

    assert any("generate_drill" in record.getMessage() for record in caplog.records)
    assert sentinel not in caplog.text


def test_timeout_is_normalized_to_agent_invocation_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "SECRET_TIMEOUT_PAYLOAD_3e68"
    runner = FakeSlowRunner(FakeSessionService())
    invoker = _make_single_runner_invoker(runner, timeout_seconds=0.01)

    with (
        caplog.at_level(logging.INFO, logger="app.agent"),
        pytest.raises(AgentInvocationError, match="timed out"),
    ):
        invoker("generate_drill", {"courseMarkdown": sentinel})

    messages = [record.getMessage() for record in caplog.records]
    assert any("task=generate_drill" in message for message in messages)
    assert any("error_type=TimeoutError" in message for message in messages)
    assert sentinel not in caplog.text


def test_missing_final_response_is_normalized_to_agent_invocation_error() -> None:
    runner = FakeNoFinalRunner(FakeSessionService())
    invoker = _make_single_runner_invoker(runner)

    with pytest.raises(AgentInvocationError, match="no final response"):
        invoker("generate_drill", {"probe": "x"})


def test_invalid_json_response_is_normalized_to_agent_invocation_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "SECRET_JSON_PAYLOAD_384d"
    runner = FakeRunner(
        name="json_agent",
        response_text="not json",
        session_service=FakeSessionService(),
    )
    invoker = _make_single_runner_invoker(runner)

    with (
        caplog.at_level(logging.INFO, logger="app.agent"),
        pytest.raises(AgentInvocationError, match="invalid JSON response"),
    ):
        invoker("generate_drill", {"courseMarkdown": sentinel})

    assert any("error_type=JSONDecodeError" in record.getMessage() for record in caplog.records)
    assert sentinel not in caplog.text


def test_runner_execution_error_is_normalized_without_logging_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "SECRET_AUTH_PAYLOAD_c19a"
    runner = FakeFailingRunner(FakeSessionService(), RuntimeError("auth failed with secret detail"))
    invoker = _make_single_runner_invoker(runner)

    with (
        caplog.at_level(logging.INFO, logger="app.agent"),
        pytest.raises(AgentInvocationError, match="agent execution failed"),
    ):
        invoker("generate_drill", {"courseMarkdown": sentinel})

    messages = [record.getMessage() for record in caplog.records]
    assert any("task=generate_drill" in message for message in messages)
    assert any("error_type=RuntimeError" in message for message in messages)
    assert "auth failed with secret detail" not in caplog.text
    assert sentinel not in caplog.text


def test_default_runner_factory_builds_four_standalone_runners_with_shared_sessions() -> None:
    runners = _default_runner_factory()

    assert set(runners) == set(TASK_NAMES)
    session_services = set()
    for task_name, runner in runners.items():
        assert isinstance(runner, Runner)
        agent = runner.agent
        assert agent is not None
        assert agent.name == TASK_TO_AGENT_NAME[task_name]
        assert agent.parent_agent is None
        session_services.add(id(runner.session_service))
        assert isinstance(runner.session_service, InMemorySessionService)
    assert len(session_services) == 1


def test_create_adk_invoker_fails_when_api_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_google_auth_env(monkeypatch)

    with pytest.raises(AdkAgentConfigurationError, match="GOOGLE_API_KEY"):
        create_adk_invoker(Settings(agent_timeout_seconds=7))


def test_create_adk_invoker_fails_when_vertex_auth_vars_are_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_google_auth_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")

    with pytest.raises(AdkAgentConfigurationError) as exc_info:
        create_adk_invoker(Settings(agent_timeout_seconds=7))

    message = str(exc_info.value)
    assert "GOOGLE_CLOUD_PROJECT" in message
    assert "GOOGLE_CLOUD_LOCATION" in message
    assert "GOOGLE_API_KEY" not in message


def test_create_adk_invoker_allows_complete_vertex_auth_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_google_auth_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-id")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "asia-northeast1")
    runner = FakeRunner(
        name="vertex_agent",
        response_text='{"ok": true}',
        session_service=FakeSessionService(),
    )

    invoker = create_adk_invoker(
        Settings(agent_timeout_seconds=7),
        runner_factory=lambda: {"generate_drill": cast(Runner, runner)},
    )

    assert invoker("generate_drill", {"probe": "x"}) == {"ok": True}


def test_create_adk_invoker_passes_settings_timeout_to_invoker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_google_auth_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_API_KEY", "fake-key")
    runner = FakeSlowRunner(FakeSessionService())
    invoker = create_adk_invoker(
        Settings(agent_timeout_seconds=0),
        runner_factory=lambda: {"generate_drill": cast(Runner, runner)},
    )

    with pytest.raises(AgentInvocationError, match="timed out"):
        invoker("generate_drill", {"probe": "x"})
