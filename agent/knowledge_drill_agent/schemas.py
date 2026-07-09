from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


class AgentModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        frozen=True,
        populate_by_name=True,
    )


class RubricItem(AgentModel):
    criterion: str
    points: int = Field(ge=0, le=4)
    required: bool = True


class SourceEvidence(AgentModel):
    section_heading: str
    excerpt: str


class DrillQuestion(AgentModel):
    id: str
    question: str = Field(
        validation_alias=AliasChoices("question", "scenario"),
        serialization_alias="question",
    )
    intent: str
    rubric: list[RubricItem]
    ideal_answer: str
    source_evidence: list[SourceEvidence] = Field(min_length=1)
    max_score: int = Field(default=4, ge=4, le=4)

    @field_validator("source_evidence", mode="before")
    @classmethod
    def normalize_source_evidence(cls, value: object) -> object:
        if isinstance(value, list):
            normalized: list[object] = []
            for item in value:
                if isinstance(item, str):
                    normalized.append({"sectionHeading": item, "excerpt": item})
                else:
                    normalized.append(item)
            return normalized
        return value

    @model_validator(mode="after")
    def validate_rubric_total(self) -> DrillQuestion:
        total = sum(item.points for item in self.rubric)
        if total != self.max_score:
            raise ValueError("rubric points must total max_score")
        return self


class DrillGenerationInput(AgentModel):
    course_title: str = Field(
        validation_alias=AliasChoices("courseTitle", "title"),
        serialization_alias="courseTitle",
    )
    course_markdown: str = Field(
        validation_alias=AliasChoices("courseMarkdown", "markdown"),
        serialization_alias="courseMarkdown",
    )
    drill_focus: str | None = Field(
        default=None,
        max_length=500,
        validation_alias=AliasChoices("drillFocus", "focus"),
        serialization_alias="drillFocus",
    )


class DrillGenerationOutput(AgentModel):
    questions: list[DrillQuestion] = Field(min_length=3, max_length=3)


class GradingInput(AgentModel):
    question: DrillQuestion
    learner_answer: str = Field(
        validation_alias=AliasChoices("learnerAnswer", "answerText", "answer_text"),
        serialization_alias="learnerAnswer",
    )


class GradingOutput(AgentModel):
    question_id: str
    score: int = Field(ge=0, le=4)
    max_score: int = Field(default=4, ge=4, le=4)
    correct_points: list[str] = Field(
        validation_alias=AliasChoices("correctPoints", "strengths"),
        serialization_alias="correctPoints",
    )
    missing_points: list[str] = Field(
        validation_alias=AliasChoices("missingPoints", "gaps"),
        serialization_alias="missingPoints",
    )
    feedback: str = Field(
        validation_alias=AliasChoices("feedback", "learnerFeedback"),
        serialization_alias="feedback",
    )
    failure_tags: list[str]

    @model_validator(mode="after")
    def validate_score_bounds(self) -> GradingOutput:
        if self.score > self.max_score:
            raise ValueError("score must not exceed max_score")
        return self


class GradedAnswerSummary(AgentModel):
    learner_name: str
    total_score: int = Field(ge=0)
    max_score: int = Field(ge=1)
    grading_results: list[GradingOutput]


class FailureSignal(AgentModel):
    id: str = Field(default_factory=lambda: f"fs_{uuid4().hex[:8]}")
    title: str
    severity: str
    evidence: list[str] = Field(min_length=1)
    likely_cause: str = Field(
        validation_alias=AliasChoices("likelyCause", "inferredCause"),
        serialization_alias="likelyCause",
    )
    suspected_document_gap: str = Field(
        validation_alias=AliasChoices("suspectedDocumentGap", "suspectedDocGap"),
        serialization_alias="suspectedDocumentGap",
    )
    target_sections: list[str] = Field(min_length=1)
    recommended_change: str
    affected_count: int = Field(ge=0)
    sample_size: int = Field(ge=1)
    confidence_note: str | None = None

    @model_validator(mode="after")
    def validate_affected_count(self) -> FailureSignal:
        if self.affected_count > self.sample_size:
            raise ValueError("affected_count must not exceed sample_size")
        return self


class FailureAnalysisInput(AgentModel):
    course_markdown: str
    questions: list[DrillQuestion]
    answers: list[GradedAnswerSummary] = Field(min_length=1)
    grading_results: list[GradingOutput]


class AnalysisPerspective(AgentModel):
    id: str
    title: str
    summary: str


class AnalysisReviewNote(AgentModel):
    id: str
    source: Literal["evidence_critic", "critic_reviewer", "finalizer"]
    timeline_step: Literal[
        "detect_failure_patterns",
        "match_course_evidence",
        "decide_patch_strategy",
    ]
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)


class FailureAnalysisOutput(AgentModel):
    failure_signals: list[FailureSignal] = Field(min_length=1)
    perspectives: list[AnalysisPerspective] = Field(default_factory=list)
    review_notes: list[AnalysisReviewNote] = Field(default_factory=list)


class ReviewedFinding(AgentModel):
    finding_id: str
    source: Literal[
        "misconception_analyst",
        "document_gap_analyst",
        "question_quality_analyst",
    ]
    summary: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)


class EvidenceReviewOutput(AgentModel):
    accepted_findings: list[ReviewedFinding] = Field(default_factory=list)
    rejected_findings: list[ReviewedFinding] = Field(default_factory=list)
    finalizer_guidance: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    revision_notes: list[str] = Field(default_factory=list)


class CriticReviewOutput(AgentModel):
    verdict: Literal["approved", "needs_revision"]
    issues: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    approved_finding_ids: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class DocumentPatchInput(AgentModel):
    course_markdown: str
    failure_signals: list[FailureSignal] = Field(min_length=1)


class DocumentPatchOutput(AgentModel):
    patched_markdown: str
    patch_summary: str
    risk_notes: list[str]
