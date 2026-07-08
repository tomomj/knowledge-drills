"""Task 2.1 verification: individual Runner execution for the 4 leaf agents.

Empirical findings against google-adk 2.3.0 (see docstrings on each test):

- ``Runner`` construction itself accepts the module-level leaf agents even
  though they are registered in ``root_agent.sub_agents`` (single-parent
  constraint sets ``parent_agent`` on them).
- However, the execution path of a parent-attached leaf uses AutoFlow and
  injects a ``transfer_to_agent`` tool plus instructions targeting the root
  agent and the sibling leaves. That conflicts with the deterministic
  task-name -> leaf-agent mapping required by the design (an LLM transfer
  could escape the Runner tree via the ``root_agent`` parent walk).
- Therefore the standalone factories (``create_*_agent``) in the agent
  package are the supported way to mount leaves on individual Runners.

No external generative AI service is contacted: the Gemini model layer is
stubbed at the ``generate_content_async`` boundary, so no credentials or
network access are required.
"""

from collections.abc import AsyncGenerator, Callable

import pytest
from google.adk.agents import Agent, BaseAgent
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from knowledge_drill_agent.agent import (
    create_document_patch_agent,
    create_drill_generator_agent,
    create_failure_analysis_agent,
    create_grading_agent,
    document_patch_agent,
    drill_generator_agent,
    failure_analysis_agent,
    grading_agent,
    root_agent,
)
from knowledge_drill_agent.samples import (
    build_sample_document_patch_output,
    build_sample_drill_generation_output,
    build_sample_failure_analysis_output,
    build_sample_grading_output,
)
from knowledge_drill_agent.schemas import (
    AgentModel,
    DocumentPatchInput,
    DrillGenerationInput,
    FailureAnalysisInput,
    GradedAnswerSummary,
    GradingInput,
)
from pydantic import BaseModel

MODEL_ENV_VAR = "KNOWLEDGE_DRILL_AGENT_MODEL"

LEAF_FACTORIES: dict[str, Callable[[], Agent]] = {
    "drill_generator_agent": create_drill_generator_agent,
    "grading_agent": create_grading_agent,
    "failure_analysis_agent": create_failure_analysis_agent,
    "document_patch_agent": create_document_patch_agent,
}

ROOT_SUB_AGENTS: dict[str, BaseAgent] = {
    "drill_generator_agent": drill_generator_agent,
    "grading_agent": grading_agent,
    "failure_analysis_agent": failure_analysis_agent,
    "document_patch_agent": document_patch_agent,
}

MODULE_LEVEL_SINGLE_LEAVES: dict[str, Agent] = {
    "drill_generator_agent": drill_generator_agent,
    "grading_agent": grading_agent,
    "document_patch_agent": document_patch_agent,
}


def _make_session_service() -> InMemorySessionService:
    # ADK 2.3.0 leaves InMemorySessionService.__init__ untyped.
    return InMemorySessionService()  # type: ignore[no-untyped-call]


def _build_payloads_and_responses() -> dict[str, tuple[AgentModel, AgentModel]]:
    """Schema-valid (input payload, canned model response) per leaf agent."""
    drill_output = build_sample_drill_generation_output()
    grading_output = build_sample_grading_output()
    analysis_output = build_sample_failure_analysis_output()
    patch_output = build_sample_document_patch_output()
    return {
        "drill_generator_agent": (
            DrillGenerationInput(course_title="講座", course_markdown="# 講座"),
            drill_output,
        ),
        "grading_agent": (
            GradingInput(question=drill_output.questions[0], learner_answer="回答"),
            grading_output,
        ),
        "failure_analysis_agent": (
            FailureAnalysisInput(
                course_markdown="# 講座",
                questions=list(drill_output.questions),
                answers=[
                    GradedAnswerSummary(
                        learner_name="受講者",
                        total_score=2,
                        max_score=4,
                        grading_results=[grading_output],
                    )
                ],
                grading_results=[grading_output],
            ),
            analysis_output,
        ),
        "document_patch_agent": (
            DocumentPatchInput(
                course_markdown="# 講座",
                failure_signals=list(analysis_output.failure_signals),
            ),
            patch_output,
        ),
    }


def _function_declaration_names(llm_request: LlmRequest) -> list[str]:
    names: list[str] = []
    if llm_request.config and llm_request.config.tools:
        for tool in llm_request.config.tools:
            declarations = getattr(tool, "function_declarations", None) or []
            names.extend(declaration.name for declaration in declarations)
    return names


def test_single_parent_constraint_premise_on_module_level_leaves() -> None:
    """Documents the conflict premise: module-level root sub-agents are parent-attached.

    Runner construction still succeeds for them in google-adk 2.3.0, so the
    conflict is behavioral (AutoFlow transfer surface), not constructional.
    """
    session_service = _make_session_service()
    for name, sub_agent in ROOT_SUB_AGENTS.items():
        assert sub_agent.parent_agent is root_agent
        runner = Runner(app_name="premise", agent=sub_agent, session_service=session_service)
        assert runner.agent is sub_agent, name


def test_standalone_factories_yield_parentless_agents_with_unchanged_contract() -> None:
    """Factories produce parent-less clones of the registered leaf definitions.

    Guards the task boundary: no prompt / schema / name / description content
    change relative to the module-level single leaf definitions where they are
    still registered directly. Failure analysis keeps its single leaf factory
    for deterministic Runner execution, while the root app can register the
    configured composed workflow.
    """
    for name, factory in LEAF_FACTORIES.items():
        standalone = factory()
        assert standalone.parent_agent is None
        assert standalone.sub_agents == []
        if name == "failure_analysis_agent":
            assert standalone.name == name
            assert standalone.output_schema is not None
            continue

        registered = MODULE_LEVEL_SINGLE_LEAVES[name]
        assert standalone is not registered
        assert standalone.name == registered.name == name
        assert standalone.description == registered.description
        assert standalone.instruction == registered.instruction
        assert standalone.input_schema is registered.input_schema
        assert standalone.output_schema is registered.output_schema


def test_each_standalone_leaf_mounts_on_individual_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All 4 leaves mount on individual Runners sharing one session service."""
    monkeypatch.setenv(MODEL_ENV_VAR, "gemini-env-probe")
    session_service = _make_session_service()
    for name, factory in LEAF_FACTORIES.items():
        agent = factory()
        runner = Runner(app_name="knowledge-drills", agent=agent, session_service=session_service)
        assert runner.agent is agent, name
        assert agent.model == "gemini-env-probe", name


def test_model_env_var_is_resolved_at_factory_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(MODEL_ENV_VAR, raising=False)
    assert create_drill_generator_agent().model == "gemini-2.5-flash-lite"

    monkeypatch.setenv(MODEL_ENV_VAR, "gemini-operational-model")
    for factory in LEAF_FACTORIES.values():
        assert factory().model == "gemini-operational-model"


async def test_execution_path_runs_each_leaf_without_external_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mounts each standalone leaf on its own Runner and drives run_async.

    The Gemini layer is stubbed to capture the outgoing LlmRequest and to
    return a schema-valid canned response, verifying:
    - the execution path completes with a final response,
    - the env-configured model name reaches the actual LLM request,
    - no transfer_to_agent surface is present (deterministic single agent).
    """
    monkeypatch.setenv(MODEL_ENV_VAR, "gemini-exec-probe")
    captured_requests: dict[str, LlmRequest] = {}
    canned: dict[str, str] = {"text": ""}

    async def fake_generate_content_async(
        self: Gemini, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        captured_requests[llm_request.model or "unknown"] = llm_request
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=canned["text"])])
        )

    monkeypatch.setattr(Gemini, "generate_content_async", fake_generate_content_async)

    session_service = _make_session_service()
    cases = _build_payloads_and_responses()
    for name, factory in LEAF_FACTORIES.items():
        payload, response_model = cases[name]
        assert isinstance(payload, BaseModel)
        assert isinstance(response_model, BaseModel)
        canned["text"] = response_model.model_dump_json(by_alias=True)
        captured_requests.clear()

        agent = factory()
        runner = Runner(app_name="knowledge-drills", agent=agent, session_service=session_service)
        await session_service.create_session(
            app_name="knowledge-drills", user_id="verifier", session_id=f"session-{name}"
        )
        events = [
            event
            async for event in runner.run_async(
                user_id="verifier",
                session_id=f"session-{name}",
                new_message=types.Content(
                    role="user",
                    parts=[types.Part(text=payload.model_dump_json(by_alias=True))],
                ),
            )
        ]

        final_events = [event for event in events if event.is_final_response()]
        assert final_events, f"{name}: no final response event"
        final_content = final_events[-1].content
        assert final_content is not None and final_content.parts
        assert final_content.parts[0].text == canned["text"], name

        llm_request = captured_requests.get("gemini-exec-probe")
        assert llm_request is not None, f"{name}: env model did not reach the LLM request"
        assert "transfer_to_agent" not in _function_declaration_names(llm_request), name
