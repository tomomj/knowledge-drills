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


settings = get_agent_settings()

drill_generator_agent = Agent(
    name="drill_generator_agent",
    model=settings.model,
    description="Generates exactly three grounded scenario-based drill questions.",
    instruction=_load_prompt("drill_generator.md"),
    input_schema=DrillGenerationInput,
    output_schema=DrillGenerationOutput,
)

grading_agent = Agent(
    name="grading_agent",
    model=settings.model,
    description="Grades learner answers against the supplied rubric without filling gaps.",
    instruction=_load_prompt("grading.md"),
    input_schema=GradingInput,
    output_schema=GradingOutput,
)

failure_analysis_agent = Agent(
    name="failure_analysis_agent",
    model=settings.model,
    description="Extracts repeated failure signals from graded answers.",
    instruction=_load_prompt("failure_analysis.md"),
    input_schema=FailureAnalysisInput,
    output_schema=FailureAnalysisOutput,
)

document_patch_agent = Agent(
    name="document_patch_agent",
    model=settings.model,
    description="Drafts minimal Markdown patches for validated failure signals.",
    instruction=_load_prompt("document_patch.md"),
    input_schema=DocumentPatchInput,
    output_schema=DocumentPatchOutput,
)

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
