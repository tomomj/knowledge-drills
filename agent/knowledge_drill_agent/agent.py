from pathlib import Path

from google.adk.agents import Agent

from knowledge_drill_agent.config import get_agent_settings
from knowledge_drill_agent.schemas import (
    DocumentPatchInput,
    DocumentPatchOutput,
    DrillGenerationInput,
    DrillGenerationOutput,
    FailureAnalysisInput,
    FailureAnalysisOutput,
    GradingInput,
    GradingOutput,
)

PROMPT_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _resolve_model(model: str | None) -> str:
    return model if model is not None else get_agent_settings().model


def create_drill_generator_agent(model: str | None = None) -> Agent:
    """Create a standalone (parent-less) drill generator agent.

    Intended for individual Runner execution. The model name defaults to the
    KNOWLEDGE_DRILL_AGENT_MODEL environment setting resolved at call time.
    """
    return Agent(
        name="drill_generator_agent",
        model=_resolve_model(model),
        description="Generates exactly three grounded scenario-based drill questions.",
        instruction=_load_prompt("drill_generator.md"),
        input_schema=DrillGenerationInput,
        output_schema=DrillGenerationOutput,
    )


def create_grading_agent(model: str | None = None) -> Agent:
    """Create a standalone (parent-less) grading agent.

    Intended for individual Runner execution. The model name defaults to the
    KNOWLEDGE_DRILL_AGENT_MODEL environment setting resolved at call time.
    """
    return Agent(
        name="grading_agent",
        model=_resolve_model(model),
        description="Grades learner answers against the supplied rubric without filling gaps.",
        instruction=_load_prompt("grading.md"),
        input_schema=GradingInput,
        output_schema=GradingOutput,
    )


def create_failure_analysis_agent(model: str | None = None) -> Agent:
    """Create a standalone (parent-less) failure analysis agent.

    Intended for individual Runner execution. The model name defaults to the
    KNOWLEDGE_DRILL_AGENT_MODEL environment setting resolved at call time.
    """
    return Agent(
        name="failure_analysis_agent",
        model=_resolve_model(model),
        description="Extracts repeated failure signals from graded answers.",
        instruction=_load_prompt("failure_analysis.md"),
        input_schema=FailureAnalysisInput,
        output_schema=FailureAnalysisOutput,
    )


def create_document_patch_agent(model: str | None = None) -> Agent:
    """Create a standalone (parent-less) document patch agent.

    Intended for individual Runner execution. The model name defaults to the
    KNOWLEDGE_DRILL_AGENT_MODEL environment setting resolved at call time.
    """
    return Agent(
        name="document_patch_agent",
        model=_resolve_model(model),
        description="Drafts minimal Markdown patches for validated failure signals.",
        instruction=_load_prompt("document_patch.md"),
        input_schema=DocumentPatchInput,
        output_schema=DocumentPatchOutput,
    )


settings = get_agent_settings()

drill_generator_agent = create_drill_generator_agent(settings.model)

grading_agent = create_grading_agent(settings.model)

failure_analysis_agent = create_failure_analysis_agent(settings.model)

document_patch_agent = create_document_patch_agent(settings.model)

root_agent = Agent(
    name="knowledge_drill_agent",
    model=settings.model,
    description=(
        "Generates drills, grades answers, analyzes failure signals, "
        "and drafts document patches."
    ),
    instruction=_load_prompt("root.md"),
    sub_agents=[
        drill_generator_agent,
        grading_agent,
        failure_analysis_agent,
        document_patch_agent,
    ],
)
