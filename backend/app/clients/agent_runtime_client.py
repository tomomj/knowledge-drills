import logging
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas import (
    DocumentPatchRequest,
    DocumentPatchResponse,
    DrillGenerationRequest,
    DrillGenerationResponse,
    FailureAnalysisRequest,
    FailureAnalysisResponse,
    GradingRequest,
    GradingResponse,
)

AgentPayload = dict[str, object]
AgentResponse = Mapping[str, object]
AgentInvoker = Callable[[str, AgentPayload], AgentResponse]
ResponseT = TypeVar("ResponseT", bound=BaseModel)
logger = logging.getLogger("app.agent")


class AgentInvocationError(Exception):
    def __init__(
        self,
        message: str,
        *,
        task_name: str | None = None,
        error_type: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.task_name = task_name
        self.error_type = error_type
        self.reason = reason


class AgentRuntimeClient:
    def __init__(self, invoker: AgentInvoker) -> None:
        self._invoker = invoker

    def generate_drill(self, request: DrillGenerationRequest) -> DrillGenerationResponse:
        return self._invoke_typed("generate_drill", request, DrillGenerationResponse)

    def grade_answer(self, request: GradingRequest) -> GradingResponse:
        return self._invoke_typed(
            "grade_answer",
            request,
            GradingResponse,
            post_validate=lambda response: self._validate_grading_response(request, response),
        )

    def analyze_failures(self, request: FailureAnalysisRequest) -> FailureAnalysisResponse:
        return self._invoke_typed(
            "analyze_failures",
            request,
            FailureAnalysisResponse,
            post_validate=lambda response: self._validate_failure_analysis_response(
                request,
                response,
            ),
        )

    def propose_document_patch(self, request: DocumentPatchRequest) -> DocumentPatchResponse:
        return self._invoke_typed("propose_document_patch", request, DocumentPatchResponse)

    def _invoke_typed(
        self,
        task_name: str,
        request: BaseModel,
        response_model: type[ResponseT],
        *,
        post_validate: Callable[[ResponseT], str | None] | None = None,
    ) -> ResponseT:
        payload = request.model_dump(mode="json", by_alias=True)
        last_error: ValidationError | str | None = None
        started_at = perf_counter()

        for attempt in range(2):
            raw_response = self._invoker(task_name, payload)
            try:
                response = response_model.model_validate(raw_response)
            except ValidationError as exc:
                last_error = exc
                logger.info(
                    "agent response validation failed task=%s attempt=%s error_count=%s",
                    task_name,
                    attempt + 1,
                    len(exc.errors()),
                )
                continue

            validation_error = post_validate(response) if post_validate is not None else None
            if validation_error is not None:
                last_error = validation_error
                logger.info(
                    "agent response validation failed task=%s attempt=%s error_count=%s",
                    task_name,
                    attempt + 1,
                    1,
                )
                continue

            logger.info(
                "agent invocation completed task=%s latency_ms=%.2f",
                task_name,
                (perf_counter() - started_at) * 1000,
            )
            return response

        error_type = (
            "ValidationError"
            if isinstance(last_error, ValidationError)
            else "ContextValidationError"
        )
        reason = _validation_failure_reason(last_error)
        logger.warning(
            "agent response validation failed permanently task=%s attempts=%s "
            "error_type=%s reason=%s latency_ms=%.2f",
            task_name,
            2,
            error_type,
            reason,
            (perf_counter() - started_at) * 1000,
        )
        raise AgentInvocationError(
            f"schema validation failed for {task_name}",
            task_name=task_name,
            error_type=error_type,
            reason=reason,
        )

    def _validate_grading_response(
        self,
        request: GradingRequest,
        response: GradingResponse,
    ) -> str | None:
        if response.question_id != request.question.id:
            return "questionId does not match request question"
        if response.score > request.question.max_score:
            return "score exceeds request question maxScore"
        return None

    def _validate_failure_analysis_response(
        self,
        request: FailureAnalysisRequest,
        response: FailureAnalysisResponse,
    ) -> str | None:
        expected_sample_size = len(request.answers)
        for signal in response.failure_signals:
            if signal.sample_size != expected_sample_size:
                return "failure signal sampleSize does not match request answers"
        return None


def _validation_failure_reason(error: ValidationError | str | None) -> str:
    if isinstance(error, ValidationError):
        details = error.errors(include_input=False)
        parts: list[str] = []
        for detail in details[:3]:
            loc_value = detail.get("loc", ())
            if isinstance(loc_value, (list, tuple)):
                loc = ".".join(str(segment) for segment in loc_value)
            else:
                loc = str(loc_value)
            error_kind = str(detail.get("type", "unknown"))
            parts.append(f"{loc or '<root>'}:{error_kind}")
        remaining_count = len(details) - len(parts)
        if remaining_count > 0:
            parts.append(f"+{remaining_count} more")
        return ",".join(parts) or "validation error"
    if isinstance(error, str) and error:
        return error
    return "unknown validation error"
