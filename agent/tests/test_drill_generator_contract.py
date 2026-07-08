import pytest
from pydantic import ValidationError

from knowledge_drill_agent.agent import drill_generator_agent
from knowledge_drill_agent.samples import build_sample_drill_generation_output
from knowledge_drill_agent.schemas import (
    DrillGenerationInput,
    DrillGenerationOutput,
    DrillQuestion,
    RubricItem,
    SourceEvidence,
)


def test_drill_generator_agent_declares_output_contract() -> None:
    assert drill_generator_agent.name == "drill_generator_agent"
    assert drill_generator_agent.input_schema is DrillGenerationInput
    assert drill_generator_agent.output_schema is DrillGenerationOutput
    instruction = drill_generator_agent.instruction
    assert isinstance(instruction, str)
    assert "必ず3問" in instruction
    assert "sourceEvidence" in instruction
    assert "question" in instruction
    assert "drillFocus" in instruction
    assert "出題観点" in instruction
    assert "完全一致" in instruction
    assert "教材に実在する内容のみ" in instruction


def test_drill_generation_input_accepts_drill_focus_aliases() -> None:
    camel_payload = DrillGenerationInput.model_validate(
        {
            "courseTitle": "講座",
            "courseMarkdown": "# Body",
            "drillFocus": "例外条件を重点的に出す",
        }
    )
    focus_payload = DrillGenerationInput.model_validate(
        {"title": "講座", "markdown": "# Body", "focus": "顧客影響"}
    )
    snake_payload = DrillGenerationInput(
        course_title="講座",
        course_markdown="# Body",
        drill_focus="判断基準",
    )

    assert camel_payload.drill_focus == "例外条件を重点的に出す"
    assert focus_payload.drill_focus == "顧客影響"
    assert snake_payload.model_dump(by_alias=True)["drillFocus"] == "判断基準"

    with pytest.raises(ValidationError):
        DrillGenerationInput(
            course_title="講座",
            course_markdown="# Body",
            drill_focus="あ" * 501,
        )


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
