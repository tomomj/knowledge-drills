import pytest
from pydantic import ValidationError

from knowledge_drill_agent.agent import grading_agent
from knowledge_drill_agent.samples import build_sample_grading_output
from knowledge_drill_agent.schemas import GradingOutput


def test_grading_agent_declares_output_contract_and_constraints() -> None:
    assert grading_agent.name == "grading_agent"
    assert grading_agent.output_schema is GradingOutput
    instruction = grading_agent.instruction
    assert isinstance(instruction, str)
    assert "do not infer" in instruction.lower()
    assert "too short" in instruction.lower()
    assert "failureTags" in instruction


def test_grading_output_schema_bounds_score_to_max_score() -> None:
    with pytest.raises(ValidationError):
        GradingOutput(
            question_id="q1",
            score=5,
            max_score=4,
            correct_points=[],
            missing_points=["根拠が不足"],
            feedback="根拠を追記してください。",
            failure_tags=["missing_evidence"],
        )


def test_local_grading_sample_output_is_schema_valid() -> None:
    output = build_sample_grading_output()

    assert isinstance(output, GradingOutput)
    assert output.score <= output.max_score
    assert output.failure_tags
