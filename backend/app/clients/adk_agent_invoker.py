"""AgentInvoker implementation backed by Google ADK leaf-agent Runners.

Maps the four backend task names deterministically to one Runner per leaf
agent (standalone factories, no root_agent transfer). Schema validation of
the response dict is owned by AgentRuntimeClient, not this module.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import Callable, Mapping

from google.adk.agents import BaseAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from knowledge_drill_agent.agent import (
    create_configured_failure_analysis_agent,
    create_document_patch_agent,
    create_drill_generator_agent,
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

_TASK_AGENT_FACTORIES: dict[str, Callable[[], BaseAgent]] = {
    "generate_drill": create_drill_generator_agent,
    "grade_answer": create_grading_agent,
    "analyze_failures": create_configured_failure_analysis_agent,
    "propose_document_patch": create_document_patch_agent,
}

_VERTEX_TRUE_VALUES = {"1", "true", "yes"}
_RETRYABLE_ERROR_NAMES = {
    "_ResourceExhaustedError",
    "ResourceExhausted",
    "TooManyRequests",
    "ServiceUnavailable",
    "InternalServerError",
    "DeadlineExceeded",
}
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_RETRY_DELAY_SECONDS: float = 8.0


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
        retry_max_attempts: int = 3,
        retry_initial_delay_seconds: float = 1.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._timeout_seconds: float = timeout_seconds
        self._retry_max_attempts: int = max(1, retry_max_attempts)
        self._retry_initial_delay_seconds: float = retry_initial_delay_seconds
        self._sleeper: Callable[[float], None] = sleeper
        factory = runner_factory if runner_factory is not None else _default_runner_factory
        self._runners: Mapping[str, Runner] = factory()

    def __call__(self, task_name: str, payload: AgentPayload) -> AgentResponse:
        runner = self._runners.get(task_name)
        if runner is None:
            raise AgentInvocationError(
                f"unknown agent task: {task_name}",
                task_name=task_name,
                error_type="UnknownTask",
                reason="unknown agent task",
            )
        logger.info("adk agent invocation started task=%s", task_name)

        for attempt in range(1, self._retry_max_attempts + 1):
            try:
                return asyncio.run(
                    asyncio.wait_for(
                        self._run_once(runner, task_name, payload),
                        timeout=self._timeout_seconds,
                    )
                )
            except AgentInvocationError as exc:
                self._log_invocation_failure(
                    task_name,
                    exc.error_type or type(exc).__name__,
                    exc.reason or "agent invocation failed",
                )
                raise
            except TimeoutError as exc:
                reason = f"timeout_seconds={self._timeout_seconds:g}"
                self._log_invocation_failure(task_name, type(exc).__name__, reason)
                raise AgentInvocationError(
                    f"agent invocation timed out task={task_name}",
                    task_name=task_name,
                    error_type=type(exc).__name__,
                    reason=reason,
                ) from exc
            except json.JSONDecodeError as exc:
                reason = f"{exc.msg} line={exc.lineno} column={exc.colno}"
                self._log_invocation_failure(task_name, type(exc).__name__, reason)
                raise AgentInvocationError(
                    f"invalid JSON response from agent task={task_name}",
                    task_name=task_name,
                    error_type=type(exc).__name__,
                    reason=reason,
                ) from exc
            except Exception as exc:
                error_type = type(exc).__name__
                reason = _agent_exception_reason(exc)
                if _is_retryable_agent_exception(exc) and attempt < self._retry_max_attempts:
                    delay_seconds = self._retry_delay_seconds(attempt)
                    logger.warning(
                        "adk agent invocation retrying task=%s error_type=%s reason=%s "
                        "attempt=%s max_attempts=%s next_delay_seconds=%.2f",
                        task_name,
                        error_type,
                        reason,
                        attempt,
                        self._retry_max_attempts,
                        delay_seconds,
                    )
                    self._sleeper(delay_seconds)
                    continue
                self._log_invocation_failure(task_name, error_type, reason)
                raise AgentInvocationError(
                    f"agent execution failed task={task_name}",
                    task_name=task_name,
                    error_type=error_type,
                    reason=reason,
                ) from exc

        raise AssertionError("unreachable agent retry loop state")

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
            raise AgentInvocationError(
                f"agent returned no final response task={task_name}",
                task_name=task_name,
                error_type="NoFinalResponse",
                reason="agent returned no final response",
            )
        parsed: AgentResponse = json.loads(final_text)
        return parsed

    def _log_invocation_failure(self, task_name: str, error_type: str, reason: str) -> None:
        logger.warning(
            "adk agent invocation failed task=%s error_type=%s reason=%s",
            task_name,
            error_type,
            reason,
        )

    def _retry_delay_seconds(self, attempt: int) -> float:
        delay = float(self._retry_initial_delay_seconds * (2 ** (attempt - 1)))
        if delay > _MAX_RETRY_DELAY_SECONDS:
            return _MAX_RETRY_DELAY_SECONDS
        return delay


def _is_retryable_agent_exception(exc: Exception) -> bool:
    status_code = _exception_status_code(exc)
    if status_code in _RETRYABLE_STATUS_CODES:
        return True
    return type(exc).__name__ in _RETRYABLE_ERROR_NAMES


def _agent_exception_reason(exc: Exception) -> str:
    parts: list[str] = []
    status_code = _exception_status_code(exc)
    if status_code is not None:
        parts.append(f"status_code={status_code}")
    if type(exc).__name__ in _RETRYABLE_ERROR_NAMES:
        parts.append(f"transient_error={type(exc).__name__}")
    message = _google_exception_message(exc)
    if message:
        parts.append(f"message={message}")
    return " ".join(parts) or "agent execution raised"


def _exception_status_code(exc: Exception) -> int | None:
    for attr_name in ("code", "status_code"):
        value = getattr(exc, attr_name, None)
        if callable(value):
            value = value()
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    return None


def _google_exception_message(exc: Exception) -> str | None:
    if not type(exc).__module__.startswith("google."):
        return None
    message = " ".join(str(exc).split())
    if not message:
        return None
    return message[:240]
