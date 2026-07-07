"""AgentInvoker implementation backed by Google ADK leaf-agent Runners.

Maps the four backend task names deterministically to one Runner per leaf
agent (standalone factories, no root_agent transfer). Schema validation of
the response dict is owned by AgentRuntimeClient, not this module.
"""

import asyncio
import json
import logging
import os
import uuid
from collections.abc import Callable, Mapping

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from knowledge_drill_agent.agent import (
    create_document_patch_agent,
    create_drill_generator_agent,
    create_failure_analysis_agent,
    create_grading_agent,
)

from app.clients.agent_runtime_client import (
    AgentInvocationError,
    AgentPayload,
    AgentResponse,
)
from app.config import Settings

logger = logging.getLogger("app.agent")

_APP_NAME = "knowledge-drills"
_USER_ID = "backend"

_TASK_AGENT_FACTORIES: dict[str, Callable[[], Agent]] = {
    "generate_drill": create_drill_generator_agent,
    "grade_answer": create_grading_agent,
    "analyze_failures": create_failure_analysis_agent,
    "propose_document_patch": create_document_patch_agent,
}

_VERTEX_TRUE_VALUES = {"1", "true", "yes"}


class AdkAgentConfigurationError(RuntimeError):
    """Raised when ADK mode is requested without required auth environment."""


def _default_runner_factory() -> Mapping[str, Runner]:
    """Build one Runner per standalone leaf agent with a shared session service."""
    # ADK 2.3.0 leaves InMemorySessionService.__init__ untyped.
    session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
    return {
        task_name: Runner(
            app_name=_APP_NAME,
            agent=agent_factory(),
            session_service=session_service,
        )
        for task_name, agent_factory in _TASK_AGENT_FACTORIES.items()
    }


def create_adk_invoker(
    settings: Settings,
    *,
    runner_factory: Callable[[], Mapping[str, Runner]] | None = None,
) -> "AdkAgentInvoker":
    missing = _missing_auth_environment(os.environ)
    if missing:
        missing_vars = ", ".join(missing)
        raise AdkAgentConfigurationError(
            f"missing ADK authentication environment variables: {missing_vars}"
        )
    return AdkAgentInvoker(
        timeout_seconds=settings.agent_timeout_seconds,
        runner_factory=runner_factory,
    )


def _missing_auth_environment(env: Mapping[str, str]) -> list[str]:
    use_vertex = env.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in _VERTEX_TRUE_VALUES
    if use_vertex:
        return [
            name
            for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")
            if not env.get(name, "").strip()
        ]
    if not env.get("GOOGLE_API_KEY", "").strip():
        return ["GOOGLE_API_KEY"]
    return []


class AdkAgentInvoker:
    """AgentInvoker protocol implementation. task_name -> leaf agent deterministic mapping."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        runner_factory: Callable[[], Mapping[str, Runner]] | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        factory = runner_factory if runner_factory is not None else _default_runner_factory
        self._runners: Mapping[str, Runner] = factory()

    def __call__(self, task_name: str, payload: AgentPayload) -> AgentResponse:
        runner = self._runners.get(task_name)
        if runner is None:
            raise AgentInvocationError(f"unknown agent task: {task_name}")
        logger.info("adk agent invocation started task=%s", task_name)
        try:
            return asyncio.run(
                asyncio.wait_for(
                    self._run_once(runner, task_name, payload),
                    timeout=self._timeout_seconds,
                )
            )
        except AgentInvocationError as exc:
            self._log_invocation_failure(task_name, type(exc).__name__)
            raise
        except TimeoutError as exc:
            self._log_invocation_failure(task_name, type(exc).__name__)
            raise AgentInvocationError(f"agent invocation timed out task={task_name}") from exc
        except json.JSONDecodeError as exc:
            self._log_invocation_failure(task_name, type(exc).__name__)
            raise AgentInvocationError(
                f"invalid JSON response from agent task={task_name}"
            ) from exc
        except Exception as exc:
            self._log_invocation_failure(task_name, type(exc).__name__)
            raise AgentInvocationError(f"agent execution failed task={task_name}") from exc

    async def _run_once(
        self, runner: Runner, task_name: str, payload: AgentPayload
    ) -> AgentResponse:
        session_id = f"{task_name}-{uuid.uuid4()}"
        await runner.session_service.create_session(
            app_name=runner.app_name,
            user_id=_USER_ID,
            session_id=session_id,
        )
        message = types.Content(
            role="user",
            parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))],
        )
        final_text: str | None = None
        async for event in runner.run_async(
            user_id=_USER_ID,
            session_id=session_id,
            new_message=message,
        ):
            if not event.is_final_response():
                continue
            if event.content is not None and event.content.parts:
                text = event.content.parts[0].text
                if text is not None:
                    final_text = text
        if final_text is None:
            raise AgentInvocationError(f"agent returned no final response task={task_name}")
        parsed: AgentResponse = json.loads(final_text)
        return parsed

    def _log_invocation_failure(self, task_name: str, error_type: str) -> None:
        logger.info(
            "adk agent invocation failed task=%s error_type=%s",
            task_name,
            error_type,
        )
