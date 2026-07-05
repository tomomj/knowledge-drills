import pytest
from pydantic import ValidationError

from knowledge_drill_agent.agent import drill_generator_agent
from knowledge_drill_agent.samples import build_sample_drill_generation_output
from knowledge_drill_agent.schemas import (
    DrillGenerationOutput,
    DrillQuestion,
    RubricItem,
    SourceEvidence,
)


def test_drill_generator_agent_declares_output_contract() -> None:
    assert drill_generator_agent.name == "drill_generator_agent"
    assert drill_generator_agent.output_schema is DrillGenerationOutput
    instruction = drill_generator_agent.instruction
    assert isinstance(instruction, str)
    assert "exactly three" in instruction.lower()
    assert "sourceEvidence" in instruction
    assert "question" in instruction


def test_drill_generation_schema_requires_three_questions() -> None:
    question = DrillQuestion(
        id="q1",
        question="判断理由を書いてください。",
        intent="判断を見る",
        rubric=[RubricItem(criterion="根拠", points=4, required=True)],
        ideal_answer="根拠に基づき判断する。",
        source_evidence=[SourceEvidence(section_heading="方針", excerpt="## 方針")],
        max_score=4,
    )

    with pytest.raises(ValidationError):
        DrillGenerationOutput(questions=[question])


def test_drill_question_schema_requires_rubric_total_four_and_source_evidence() -> None:
    with pytest.raises(ValidationError):
        DrillQuestion(
            id="q1",
            question="判断理由を書いてください。",
            intent="判断を見る",
            rubric=[RubricItem(criterion="根拠", points=3, required=True)],
            ideal_answer="根拠に基づき判断する。",
            source_evidence=[SourceEvidence(section_heading="方針", excerpt="## 方針")],
            max_score=4,
        )

    with pytest.raises(ValidationError):
        DrillQuestion(
            id="q1",
            question="判断理由を書いてください。",
            intent="判断を見る",
            rubric=[RubricItem(criterion="根拠", points=4, required=True)],
            ideal_answer="根拠に基づき判断する。",
            source_evidence=[],
            max_score=4,
        )


def test_local_sample_output_is_schema_valid() -> None:
    output = build_sample_drill_generation_output()

    assert isinstance(output, DrillGenerationOutput)
    assert len(output.questions) == 3
    assert all(question.max_score == 4 for question in output.questions)
