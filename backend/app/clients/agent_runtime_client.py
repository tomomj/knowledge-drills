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
    pass


class AgentRuntimeClient:
    def __init__(self, invoker: AgentInvoker) -> None:
        self._invoker = invoker

    def generate_drill(self, request: DrillGenerationRequest) -> DrillGenerationResponse:
        return self._invoke_typed("generate_drill", request, DrillGenerationResponse)

    def grade_answer(self, request: GradingRequest) -> GradingResponse:
        return self._invoke_typed("grade_answer", request, GradingResponse)

    def analyze_failures(self, request: FailureAnalysisRequest) -> FailureAnalysisResponse:
        return self._invoke_typed("analyze_failures", request, FailureAnalysisResponse)

    def propose_document_patch(self, request: DocumentPatchRequest) -> DocumentPatchResponse:
        return self._invoke_typed("propose_document_patch", request, DocumentPatchResponse)

    def _invoke_typed(
        self,
        task_name: str,
        request: BaseModel,
        response_model: type[ResponseT],
    ) -> ResponseT:
        payload = request.model_dump(mode="json", by_alias=True)
        last_error: ValidationError | None = None
        started_at = perf_counter()

        for attempt in range(2):
            raw_response = self._invoker(task_name, payload)
            try:
                response = response_model.model_validate(raw_response)
                logger.info(
                    "agent invocation completed task=%s latency_ms=%.2f",
                    task_name,
                    (perf_counter() - started_at) * 1000,
                )
                return response
            except ValidationError as exc:
                last_error = exc
                logger.info(
                    "agent response validation failed task=%s attempt=%s error_count=%s",
                    task_name,
                    attempt + 1,
                    len(exc.errors()),
                )

        raise AgentInvocationError(f"schema validation failed for {task_name}: {last_error}")
