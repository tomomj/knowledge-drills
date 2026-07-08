from typing import Any, cast

import pytest
from google.adk.agents import Agent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.tools.exit_loop_tool import exit_loop
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
    AnalysisReviewNote,
    CriticReviewOutput,
    DocumentPatchOutput,
    EvidenceReviewOutput,
    FailureAnalysisInput,
    FailureAnalysisOutput,
    FailureSignal,
    ReviewedFinding,
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
    assert len(composite.sub_agents) == 3

    analyst_parallel = composite.sub_agents[0]
    review_loop = composite.sub_agents[1]
    finalizer = composite.sub_agents[2]
    assert isinstance(analyst_parallel, ParallelAgent)
    assert analyst_parallel.name == "analyst_parallel"
    assert isinstance(review_loop, LoopAgent)
    assert review_loop.name == "review_loop"
    assert review_loop.max_iterations == 3
    assert isinstance(finalizer, Agent)
    assert len(analyst_parallel.sub_agents) == 3

    analyst_agents = analyst_parallel.sub_agents
    assert {agent.name for agent in analyst_agents} == {
        "failure_misconception_analyst",
        "failure_document_gap_analyst",
        "failure_question_quality_analyst",
    }
    assert {agent.output_key for agent in analyst_agents if isinstance(agent, Agent)} == {
        "misconception_findings",
        "doc_gap_findings",
        "question_quality_findings",
    }
    for analyst_agent in analyst_agents:
        assert isinstance(analyst_agent, Agent)
        assert analyst_agent.model == "gemini-contract-probe"
        assert analyst_agent.input_schema is FailureAnalysisInput
        assert analyst_agent.output_schema is None

    assert len(review_loop.sub_agents) == 2
    evidence_critic = review_loop.sub_agents[0]
    critic_reviewer = review_loop.sub_agents[1]
    assert isinstance(evidence_critic, Agent)
    assert isinstance(critic_reviewer, Agent)
    assert evidence_critic.name == "evidence_critic"
    assert evidence_critic.output_key == "evidence_review"
    assert evidence_critic.output_schema is EvidenceReviewOutput
    assert critic_reviewer.name == "critic_reviewer"
    assert critic_reviewer.output_key == "critic_review"
    assert critic_reviewer.output_schema is CriticReviewOutput
    assert exit_loop in critic_reviewer.tools

    assert finalizer.name == "failure_analysis_finalizer"
    assert finalizer.model == "gemini-contract-probe"
    assert finalizer.input_schema is FailureAnalysisInput
    assert finalizer.output_schema is FailureAnalysisOutput
    assert finalizer.output_key is None
    assert isinstance(finalizer.instruction, str)
    assert "misconception_findings" in finalizer.instruction
    assert "doc_gap_findings" in finalizer.instruction
    assert "question_quality_findings" in finalizer.instruction
    assert "approvedFindingIds" in finalizer.instruction


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


def test_failure_analysis_review_loop_schemas_use_camel_case_contracts() -> None:
    accepted = ReviewedFinding(
        finding_id="finding-1",
        source="document_gap_analyst",
        summary="例外条件の教材説明が薄い",
        rationale="採点結果で例外条件への言及不足が複数ある",
        evidence=["2 件の回答で例外条件に触れていない"],
    )
    evidence_review = EvidenceReviewOutput(
        accepted_findings=[accepted],
        rejected_findings=[],
        finalizer_guidance=["finding-1 だけを Failure Signal の根拠にする"],
        risks=["少数回答のため confidenceNote を残す"],
        revision_notes=["reviewer 指摘に基づき evidence を採点結果に限定した"],
    )
    critic_review = CriticReviewOutput(
        verdict="approved",
        issues=[],
        revision_instructions=[],
        approved_finding_ids=["finding-1"],
        risk_notes=["未承認 finding は採用しない"],
    )
    review_note = AnalysisReviewNote(
        id="critic-review-1",
        source="critic_reviewer",
        timeline_step="decide_patch_strategy",
        title="採用所見のレビュー",
        summary="finding-1 の根拠は採用可能",
        evidence=["approvedFindingIds: finding-1"],
    )
    output = FailureAnalysisOutput(
        failure_signals=[
            FailureSignal(
                title="例外条件の説明不足",
                severity="medium",
                evidence=["2 件の回答で例外条件に触れていない"],
                likely_cause="例外条件の説明が短い",
                suspected_document_gap="判断基準の例外条件が不足",
                target_sections=["## 判断基準"],
                recommended_change="例外条件の判断例を追加する",
                sample_size=2,
            )
        ],
        review_notes=[review_note],
    )

    assert evidence_review.model_dump(by_alias=True)["acceptedFindings"][0]["findingId"] == (
        "finding-1"
    )
    assert critic_review.model_dump(by_alias=True)["approvedFindingIds"] == ["finding-1"]
    assert output.model_dump(by_alias=True)["reviewNotes"][0]["timelineStep"] == (
        "decide_patch_strategy"
    )


def test_critic_review_rejects_unknown_verdict() -> None:
    with pytest.raises(ValidationError):
        CriticReviewOutput(verdict=cast(Any, "rejected"))


def test_local_analysis_and_patch_samples_are_schema_valid() -> None:
    analysis = build_sample_failure_analysis_output()
    patch = build_sample_document_patch_output()

    assert isinstance(analysis, FailureAnalysisOutput)
    assert analysis.failure_signals[0].sample_size == 2
    assert analysis.failure_signals[0].confidence_note
    assert len(analysis.perspectives) == 3
    assert isinstance(patch, DocumentPatchOutput)
    assert patch.risk_notes
