from pathlib import Path

from google.adk.agents import Agent, BaseAgent, LoopAgent, ParallelAgent, SequentialAgent

from knowledge_drill_agent.config import AnalysisMode, get_agent_settings
from knowledge_drill_agent.failure_analysis_workflow import (
    ApprovedFindingsGate,
    ReviewLoopGate,
    ensure_partial_review_note,
)
from knowledge_drill_agent.schemas import (
    CriticReviewOutput,
    DocumentPatchInput,
    DocumentPatchOutput,
    DrillGenerationInput,
    DrillGenerationOutput,
    EvidenceReviewOutput,
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

    Analyst agents write findings into session state in parallel, then a bounded
    critic/reviewer loop validates those findings before the finalizer emits the
    stable backend response contract.
    """
    misconception_analyst = _create_failure_analysis_lens_agent(
        name="failure_misconception_analyst",
        description="受講者回答に繰り返し現れるつまずきパターンを分析する。",
        prompt_name="failure_analysis_learner_pattern_lens.md",
        output_key="misconception_findings",
        model=model,
    )
    document_gap_analyst = _create_failure_analysis_lens_agent(
        name="failure_document_gap_analyst",
        description="教材側の説明不足や曖昧さに絞って誤答傾向を分析する。",
        prompt_name="failure_analysis_material_gap_lens.md",
        output_key="doc_gap_findings",
        model=model,
    )
    question_quality_analyst = _create_failure_analysis_lens_agent(
        name="failure_question_quality_analyst",
        description="設問や rubric が誤答を誘発していないかを分析する。",
        prompt_name="failure_analysis_question_quality_lens.md",
        output_key="question_quality_findings",
        model=model,
    )
    analyst_parallel = ParallelAgent(
        name="analyst_parallel",
        description="教材・設問・受講者の3視点で失敗傾向を並列分析する。",
        sub_agents=[
            misconception_analyst,
            document_gap_analyst,
            question_quality_analyst,
        ],
    )
    evidence_critic = Agent(
        name="evidence_critic",
        model=_resolve_model(model),
        description="並列分析結果を根拠の強さで採用・棄却し、finalizer への指示を作る。",
        instruction=_load_prompt("failure_analysis_evidence_critic.md"),
        input_schema=FailureAnalysisInput,
        output_schema=EvidenceReviewOutput,
        output_key="evidence_review",
    )
    critic_reviewer = Agent(
        name="critic_reviewer",
        model=_resolve_model(model),
        description="evidence critic の評価妥当性をレビューし、承認済み finding ID を明示する。",
        instruction=_load_prompt("failure_analysis_critic_reviewer.md"),
        input_schema=FailureAnalysisInput,
        output_schema=CriticReviewOutput,
        output_key="critic_review",
    )
    review_loop = LoopAgent(
        name="review_loop",
        description="根拠評価とレビューを最大3回まで繰り返す。",
        sub_agents=[evidence_critic, critic_reviewer, ReviewLoopGate()],
        max_iterations=3,
    )
    approved_findings_gate = ApprovedFindingsGate()
    finalizer = Agent(
        name="failure_analysis_finalizer",
        model=_resolve_model(model),
        description="レビュー承認済み finding だけから最終 FailureAnalysisOutput を返す。",
        instruction=_load_prompt("failure_analysis_finalizer.md"),
        input_schema=FailureAnalysisInput,
        output_schema=FailureAnalysisOutput,
        after_model_callback=ensure_partial_review_note,
    )
    return SequentialAgent(
        name="failure_analysis_agent",
        description="並列分析、根拠評価、レビュー、最終化により Failure Signal を抽出する。",
        sub_agents=[analyst_parallel, review_loop, approved_findings_gate, finalizer],
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
