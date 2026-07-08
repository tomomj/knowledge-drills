import pytest
from google.adk.agents import Agent, ParallelAgent, SequentialAgent
from pydantic import ValidationError

from knowledge_drill_agent.agent import (
    create_composite_failure_analysis_agent,
    create_configured_failure_analysis_agent,
    create_failure_analysis_agent,
    document_patch_agent,
)
from knowledge_drill_agent.samples import (
    build_sample_document_patch_output,
    build_sample_failure_analysis_output,
)
from knowledge_drill_agent.schemas import (
    AnalysisPerspective,
    DocumentPatchOutput,
    FailureAnalysisInput,
    FailureAnalysisOutput,
    FailureSignal,
)


def test_failure_analysis_agent_declares_schema_and_constraints() -> None:
    failure_analysis_agent = create_failure_analysis_agent()

    assert failure_analysis_agent.output_schema is FailureAnalysisOutput
    instruction = failure_analysis_agent.instruction
    assert isinstance(instruction, str)
    assert "sampleSize" in instruction
    assert "confidenceNote" in instruction
    assert "受講者を責めない" in instruction
    assert "社内ルール" in instruction
    assert "perspectives" in instruction
    assert "教材ギャップ" in instruction


def test_composite_failure_analysis_agent_runs_lenses_then_synthesis() -> None:
    composite = create_composite_failure_analysis_agent("gemini-contract-probe")

    assert isinstance(composite, SequentialAgent)
    assert composite.name == "failure_analysis_agent"
    assert composite.parent_agent is None
    assert len(composite.sub_agents) == 2

    lens_parallel = composite.sub_agents[0]
    synthesis_agent = composite.sub_agents[1]
    assert isinstance(lens_parallel, ParallelAgent)
    assert isinstance(synthesis_agent, Agent)
    assert len(lens_parallel.sub_agents) == 3

    lens_agents = lens_parallel.sub_agents
    assert {agent.name for agent in lens_agents} == {
        "failure_material_gap_lens",
        "failure_question_quality_lens",
        "failure_learner_pattern_lens",
    }
    assert {agent.output_key for agent in lens_agents if isinstance(agent, Agent)} == {
        "material_gap_perspective",
        "question_quality_perspective",
        "learner_pattern_perspective",
    }
    for lens_agent in lens_agents:
        assert isinstance(lens_agent, Agent)
        assert lens_agent.model == "gemini-contract-probe"
        assert lens_agent.input_schema is FailureAnalysisInput
        assert lens_agent.output_schema is None

    assert synthesis_agent.model == "gemini-contract-probe"
    assert synthesis_agent.input_schema is FailureAnalysisInput
    assert synthesis_agent.output_schema is FailureAnalysisOutput
    assert isinstance(synthesis_agent.instruction, str)
    assert "material_gap_perspective" in synthesis_agent.instruction
    assert "question_quality_perspective" in synthesis_agent.instruction
    assert "learner_pattern_perspective" in synthesis_agent.instruction


def test_configured_failure_analysis_agent_switches_modes() -> None:
    single = create_configured_failure_analysis_agent(
        "gemini-contract-probe",
        analysis_mode="single",
    )
    composed = create_configured_failure_analysis_agent(
        "gemini-contract-probe",
        analysis_mode="composed",
    )

    assert isinstance(single, Agent)
    assert single.output_schema is FailureAnalysisOutput
    assert isinstance(composed, SequentialAgent)


def test_document_patch_agent_declares_schema_and_constraints() -> None:
    assert document_patch_agent.output_schema is DocumentPatchOutput
    instruction = document_patch_agent.instruction
    assert isinstance(instruction, str)
    assert "riskNotes" in instruction
    assert "最小限で有用な Markdown" in instruction
    assert "targetSections" in instruction
    assert "申請フォーム" in instruction
    assert "confidenceNote" in instruction


def test_failure_signal_requires_core_fields_and_sample_size() -> None:
    with pytest.raises(ValidationError):
        FailureSignal(
            title="判断基準の混同",
            severity="medium",
            evidence=[],
            likely_cause="説明が薄い",
            suspected_document_gap="例が不足",
            target_sections=["## 方針"],
            recommended_change="例を追記",
            sample_size=0,
        )


def test_failure_analysis_output_accepts_optional_perspectives() -> None:
    existing_output = FailureAnalysisOutput(
        failure_signals=[
            FailureSignal(
                title="判断基準の混同",
                severity="medium",
                evidence=["2 件の回答で例外条件に触れていない"],
                likely_cause="条件分岐の説明が不足している",
                suspected_document_gap="例外時の判断基準が薄い",
                target_sections=["## 対応方針"],
                recommended_change="例外条件を追記する",
                sample_size=2,
            )
        ]
    )
    output_with_perspectives = FailureAnalysisOutput(
        failure_signals=existing_output.failure_signals,
        perspectives=[
            AnalysisPerspective(
                id="material_gap",
                title="教材ギャップ",
                summary="例外条件の説明不足が見られます",
            )
        ],
    )

    assert existing_output.perspectives == []
    assert output_with_perspectives.model_dump(by_alias=True)["perspectives"][0]["summary"] == (
        "例外条件の説明不足が見られます"
    )


def test_local_analysis_and_patch_samples_are_schema_valid() -> None:
    analysis = build_sample_failure_analysis_output()
    patch = build_sample_document_patch_output()

    assert isinstance(analysis, FailureAnalysisOutput)
    assert analysis.failure_signals[0].sample_size == 2
    assert analysis.failure_signals[0].confidence_note
    assert len(analysis.perspectives) == 3
    assert isinstance(patch, DocumentPatchOutput)
    assert patch.risk_notes
