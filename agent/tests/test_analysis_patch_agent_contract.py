import pytest
from pydantic import ValidationError

from knowledge_drill_agent.agent import document_patch_agent, failure_analysis_agent
from knowledge_drill_agent.samples import (
    build_sample_document_patch_output,
    build_sample_failure_analysis_output,
)
from knowledge_drill_agent.schemas import (
    DocumentPatchOutput,
    FailureAnalysisOutput,
    FailureSignal,
)


def test_failure_analysis_agent_declares_schema_and_constraints() -> None:
    assert failure_analysis_agent.output_schema is FailureAnalysisOutput
    instruction = failure_analysis_agent.instruction
    assert isinstance(instruction, str)
    assert "sampleSize" in instruction
    assert "confidenceNote" in instruction
    assert "受講者を責めない" in instruction
    assert "社内ルール" in instruction


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


def test_local_analysis_and_patch_samples_are_schema_valid() -> None:
    analysis = build_sample_failure_analysis_output()
    patch = build_sample_document_patch_output()

    assert isinstance(analysis, FailureAnalysisOutput)
    assert analysis.failure_signals[0].sample_size == 2
    assert analysis.failure_signals[0].confidence_note
    assert isinstance(patch, DocumentPatchOutput)
    assert patch.risk_notes
