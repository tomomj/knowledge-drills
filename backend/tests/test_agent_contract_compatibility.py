import json
from pathlib import Path
from typing import Any, cast

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.schemas import (
    DocumentPatchResponse,
    DrillGenerationRequest,
    DrillGenerationResponse,
    FailureAnalysisResponse,
    GradingRequest,
    GradingResponse,
)

SAMPLE_OUTPUT_DIR = Path(__file__).parents[2] / "agent" / "knowledge_drill_agent" / "sample_outputs"
FORBIDDEN_KEYS = {"firestorePath", "secret", "adminToken"}


def _load_sample(name: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((SAMPLE_OUTPUT_DIR / name).read_text(encoding="utf-8")),
    )


def _contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            key in FORBIDDEN_KEYS or _contains_forbidden_key(child) for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(child) for child in value)
    return False


def test_agent_sample_outputs_validate_against_backend_agent_schemas() -> None:
    DrillGenerationResponse.model_validate(_load_sample("drill_generation.json"))
    GradingResponse.model_validate(_load_sample("grading.json"))
    FailureAnalysisResponse.model_validate(_load_sample("failure_analysis.json"))
    DocumentPatchResponse.model_validate(_load_sample("document_patch.json"))


def test_agent_invocation_payload_excludes_forbidden_operational_fields() -> None:
    observed_payloads: list[dict[str, object]] = []

    def invoke(_task_name: str, payload: dict[str, object]) -> dict[str, object]:
        observed_payloads.append(payload)
        return _load_sample("drill_generation.json")

    client = AgentRuntimeClient(invoker=invoke)

    client.generate_drill(DrillGenerationRequest(course_title="講座", course_markdown="# Body"))

    assert observed_payloads
    assert not _contains_forbidden_key(observed_payloads[0])


def test_grading_invocation_payload_excludes_forbidden_operational_fields() -> None:
    observed_payloads: list[dict[str, object]] = []
    drill_output = DrillGenerationResponse.model_validate(_load_sample("drill_generation.json"))

    def invoke(_task_name: str, payload: dict[str, object]) -> dict[str, object]:
        observed_payloads.append(payload)
        return _load_sample("grading.json")

    client = AgentRuntimeClient(invoker=invoke)

    client.grade_answer(GradingRequest(question=drill_output.questions[0], learner_answer="回答"))

    assert observed_payloads
    assert not _contains_forbidden_key(observed_payloads[0])
