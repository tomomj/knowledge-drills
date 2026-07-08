from pathlib import Path

from google.adk.agents import Agent, BaseAgent, ParallelAgent, SequentialAgent

from knowledge_drill_agent.config import AnalysisMode, get_agent_settings
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
        description="講座 Markdown に根拠のある実務シナリオ型ドリルを必ず3問生成する。",
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
        description=(
            "受講者回答を提供された rubric に基づき、"
            "書かれていない内容を補わずに採点する。"
        ),
        instruction=_load_prompt("grading.md"),
        input_schema=GradingInput,
        output_schema=GradingOutput,
    )


def create_failure_analysis_agent(model: str | None = None) -> Agent:
    """Create a standalone (parent-less) failure analysis agent.

    Intended for single-agent execution. The model name defaults to the
    KNOWLEDGE_DRILL_AGENT_MODEL environment setting resolved at call time.
    """
    return Agent(
        name="failure_analysis_agent",
        model=_resolve_model(model),
        description="採点済み回答から繰り返し発生している Failure Signal を抽出する。",
        instruction=_load_prompt("failure_analysis.md"),
        input_schema=FailureAnalysisInput,
        output_schema=FailureAnalysisOutput,
    )


def _create_failure_analysis_lens_agent(
    *,
    name: str,
    description: str,
    prompt_name: str,
    output_key: str,
    model: str | None = None,
) -> Agent:
    return Agent(
        name=name,
        model=_resolve_model(model),
        description=description,
        instruction=_load_prompt(prompt_name),
        input_schema=FailureAnalysisInput,
        output_key=output_key,
    )


def create_composite_failure_analysis_agent(model: str | None = None) -> BaseAgent:
    """Create a parent-less composed failure analysis workflow.

    Three lens agents write perspective notes into session state in parallel.
    The synthesis agent is the only child with the final FailureAnalysisOutput
    schema, preserving the backend response contract.
    """
    material_gap_lens = _create_failure_analysis_lens_agent(
        name="failure_material_gap_lens",
        description="教材側の説明不足や曖昧さに絞って誤答傾向を分析する。",
        prompt_name="failure_analysis_material_gap_lens.md",
        output_key="material_gap_perspective",
        model=model,
    )
    question_quality_lens = _create_failure_analysis_lens_agent(
        name="failure_question_quality_lens",
        description="設問や rubric が誤答を誘発していないかを分析する。",
        prompt_name="failure_analysis_question_quality_lens.md",
        output_key="question_quality_perspective",
        model=model,
    )
    learner_pattern_lens = _create_failure_analysis_lens_agent(
        name="failure_learner_pattern_lens",
        description="受講者回答に繰り返し現れるつまずきパターンを分析する。",
        prompt_name="failure_analysis_learner_pattern_lens.md",
        output_key="learner_pattern_perspective",
        model=model,
    )
    lens_parallel = ParallelAgent(
        name="failure_analysis_lens_parallel",
        description="教材・設問・受講者の3視点で失敗傾向を並列分析する。",
        sub_agents=[material_gap_lens, question_quality_lens, learner_pattern_lens],
    )
    synthesis_agent = Agent(
        name="failure_analysis_synthesis_agent",
        model=_resolve_model(model),
        description="3視点の分析メモを統合し、最終 Failure Signal を返す。",
        instruction=_load_prompt("failure_analysis_synthesis.md"),
        input_schema=FailureAnalysisInput,
        output_schema=FailureAnalysisOutput,
    )
    return SequentialAgent(
        name="failure_analysis_agent",
        description="3視点の並列分析と統合により Failure Signal を抽出する。",
        sub_agents=[lens_parallel, synthesis_agent],
    )


def create_configured_failure_analysis_agent(
    model: str | None = None,
    analysis_mode: AnalysisMode | None = None,
) -> BaseAgent:
    mode = analysis_mode if analysis_mode is not None else get_agent_settings().analysis_mode
    if mode == "single":
        return create_failure_analysis_agent(model)
    return create_composite_failure_analysis_agent(model)


def create_document_patch_agent(model: str | None = None) -> Agent:
    """Create a standalone (parent-less) document patch agent.

    Intended for individual Runner execution. The model name defaults to the
    KNOWLEDGE_DRILL_AGENT_MODEL environment setting resolved at call time.
    """
    return Agent(
        name="document_patch_agent",
        model=_resolve_model(model),
        description="検証済みの Failure Signal に対応する最小限の Markdown patch 案を作成する。",
        instruction=_load_prompt("document_patch.md"),
        input_schema=DocumentPatchInput,
        output_schema=DocumentPatchOutput,
    )


settings = get_agent_settings()

drill_generator_agent = create_drill_generator_agent(settings.model)

grading_agent = create_grading_agent(settings.model)

failure_analysis_agent = create_configured_failure_analysis_agent(
    settings.model,
    settings.analysis_mode,
)

document_patch_agent = create_document_patch_agent(settings.model)

root_agent = Agent(
    name="knowledge_drill_agent",
    model=settings.model,
    description=(
        "ドリル生成、回答採点、Failure Signal 分析、"
        "講座 Markdown patch 案作成を行う。"
    ),
    instruction=_load_prompt("root.md"),
    sub_agents=[
        drill_generator_agent,
        grading_agent,
        failure_analysis_agent,
        document_patch_agent,
    ],
)
