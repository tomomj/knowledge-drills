from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


def to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        frozen=True,
        populate_by_name=True,
    )


class HealthResponse(ApiModel):
    status: str
    environment: str


class ErrorResponse(ApiModel):
    code: str
    message: str
    request_id: str = Field(alias="requestId")
    current_status: str | None = None


class UserProfile(ApiModel):
    uid: str
    email: str | None = None
    display_name: str | None = None
    photo_url: str | None = None
    created_at: str
    last_login_at: str
    demo_seeded_at: str | None = None


class CurrentUserResponse(UserProfile):
    pass


class DrillRunStatus(StrEnum):
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"


class AnswerStatus(StrEnum):
    GRADING = "grading"
    GRADED = "graded"
    FAILED = "failed"


class PatchStatus(StrEnum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    REJECTED = "rejected"
    STALE = "stale"


class FailureSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AnalysisStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AnalysisReviewSource(StrEnum):
    EVIDENCE_CRITIC = "evidence_critic"
    CRITIC_REVIEWER = "critic_reviewer"
    FINALIZER = "finalizer"


class AnalysisReviewTimelineStep(StrEnum):
    DETECT_FAILURE_PATTERNS = "detect_failure_patterns"
    MATCH_COURSE_EVIDENCE = "match_course_evidence"
    DECIDE_PATCH_STRATEGY = "decide_patch_strategy"


class CourseScoreTrendPoint(ApiModel):
    course_version: int
    average_score: float
    max_score: int


class Course(ApiModel):
    id: str
    owner_user_id: str | None = None
    title: str
    markdown: str
    drill_focus: str | None = Field(default=None, max_length=500)
    version: int = 1
    updated_at: str | None = None
    latest_drill_run_id: str | None = None
    latest_drill_status: DrillRunStatus | None = None
    answer_count: int = 0
    latest_patch_id: str | None = None
    latest_patch_status: PatchStatus | None = None
    score_trend: list[CourseScoreTrendPoint] | None = None
    is_demo: bool = False


class CourseCreateRequest(ApiModel):
    title: str
    markdown: str
    drill_focus: str | None = Field(default=None, max_length=500)


class CourseUpdateRequest(ApiModel):
    title: str
    markdown: str
    drill_focus: str | None = Field(default=None, max_length=500)


class CourseDetailResponse(ApiModel):
    id: str
    title: str
    markdown: str
    drill_focus: str | None = Field(default=None, max_length=500)
    version: int
    updated_at: str | None = None
    latest_drill_run_id: str | None = None
    latest_patch_id: str | None = None


class CourseCreateResponse(ApiModel):
    course_id: str


class CourseSummary(ApiModel):
    id: str
    title: str
    version: int
    updated_at: str | None = None
    drill_status: DrillRunStatus | None = None
    answer_count: int = 0
    patch_status: PatchStatus | None = None
    latest_drill_run_id: str | None = None
    latest_patch_id: str | None = None
    score_trend: list[CourseScoreTrendPoint] | None = None
    is_demo: bool = False


class CourseListResponse(ApiModel):
    courses: list[CourseSummary]


class CourseRevision(ApiModel):
    course_id: str
    version: int
    title: str
    markdown: str
    drill_focus: str | None = Field(default=None, max_length=500)
    updated_at: str | None = None


class CourseRevisionSummary(ApiModel):
    version: int
    title: str
    updated_at: str | None = None


class CourseRevisionListResponse(ApiModel):
    revisions: list[CourseRevisionSummary]


class CourseRevisionDiffResponse(ApiModel):
    from_version: int
    to_version: int
    diff_text: str


class RubricItem(ApiModel):
    criterion: str
    points: int = Field(ge=0, le=4)
    required: bool = True


class SourceEvidence(ApiModel):
    section_heading: str
    excerpt: str


class AnalysisTimelineItem(ApiModel):
    id: str
    title: str
    status: AnalysisStepStatus
    summary: str | None = None
    evidence: list[str] = Field(default_factory=list)
    completed_at: str | None = None


class DrillQuestion(ApiModel):
    id: str
    question: str = Field(
        validation_alias=AliasChoices("question", "scenario"),
        serialization_alias="question",
    )
    intent: str
    rubric: list[RubricItem]
    ideal_answer: str
    source_evidence: list[SourceEvidence] = Field(min_length=1)
    max_score: int = Field(default=4, ge=1, le=4)

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

    @property
    def scenario(self) -> str:
        return self.question


class DrillRun(ApiModel):
    id: str
    course_id: str
    course_version: int = 1
    drill_focus: str | None = Field(default=None, max_length=500)
    status: DrillRunStatus
    questions: list[DrillQuestion] = Field(default_factory=list)
    analysis_timeline: list[AnalysisTimelineItem] = Field(default_factory=list)
    share_token: str | None = None
    error_message: str | None = None


class GradingResult(ApiModel):
    question_id: str
    score: int = Field(ge=0, le=4)
    max_score: int = Field(default=4, ge=1, le=4)
    correct_points: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("correctPoints", "strengths"),
        serialization_alias="correctPoints",
    )
    missing_points: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("missingPoints", "gaps"),
        serialization_alias="missingPoints",
    )
    feedback: str = Field(
        validation_alias=AliasChoices("feedback", "learnerFeedback"),
        serialization_alias="feedback",
    )
    failure_tags: list[str] = Field(default_factory=list)

    @property
    def strengths(self) -> list[str]:
        return self.correct_points

    @property
    def gaps(self) -> list[str]:
        return self.missing_points

    @property
    def learner_feedback(self) -> str:
        return self.feedback


class AnswerSubmission(ApiModel):
    id: str
    course_id: str | None = None
    drill_run_id: str
    learner_name: str
    status: AnswerStatus
    answers: dict[str, str]
    grading_results: list[GradingResult] = Field(default_factory=list)
    total_score: int | None = None
    max_score: int | None = None
    error_message: str | None = None


class AnswerInput(ApiModel):
    question_id: str
    answer_text: str


class SubmitAnswerRequest(ApiModel):
    learner_name: str
    answers: list[AnswerInput]


class SubmitAnswerResponse(ApiModel):
    answer_id: str
    status: AnswerStatus
    feedback: list[str]


class FailureSignal(ApiModel):
    id: str = Field(default_factory=lambda: f"fs_{uuid4().hex[:8]}")
    title: str
    severity: FailureSeverity
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
    sample_size: int = Field(ge=1)
    confidence_note: str | None = None

    @property
    def inferred_cause(self) -> str:
        return self.likely_cause

    @property
    def suspected_doc_gap(self) -> str:
        return self.suspected_document_gap


class AnalysisPerspective(ApiModel):
    id: str
    title: str
    summary: str


class AnalysisReviewNote(ApiModel):
    id: str
    source: AnalysisReviewSource
    timeline_step: AnalysisReviewTimelineStep
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)


class DocumentPatch(ApiModel):
    id: str
    course_id: str
    drill_run_id: str
    status: PatchStatus
    base_markdown: str
    patched_markdown: str
    patch_summary: str
    risk_notes: list[str] = Field(default_factory=list)
    diff_text: str
    failure_signals: list[FailureSignal] = Field(default_factory=list)
    analysis_timeline: list[AnalysisTimelineItem] = Field(default_factory=list)
    owner_feedback: str | None = None


class PatchDecisionRequest(ApiModel):
    owner_feedback: str | None = None


class AdminDrillQuestionResponse(ApiModel):
    id: str
    question: str
    intent: str
    rubric: list[RubricItem]
    ideal_answer: str
    source_evidence: list[SourceEvidence]
    max_score: int

    @classmethod
    def from_domain(cls, question: DrillQuestion) -> AdminDrillQuestionResponse:
        return cls.model_validate(question.model_dump())


class LearnerDrillQuestionResponse(ApiModel):
    id: str
    question: str
    max_score: int

    @classmethod
    def from_domain(cls, question: DrillQuestion) -> LearnerDrillQuestionResponse:
        return cls(
            id=question.id,
            question=question.question,
            max_score=question.max_score,
        )


class QuestionScoreSummary(ApiModel):
    question_id: str
    average_score: float | None = None
    max_score: int
    graded_answer_count: int
    common_missing_points: list[str] = Field(default_factory=list)
    failure_tags: list[str] = Field(default_factory=list)


class DrillScoreSummary(ApiModel):
    graded_answer_count: int
    average_score: float | None = None
    max_score: int
    questions: list[QuestionScoreSummary] = Field(default_factory=list)


class DrillAdminResponse(ApiModel):
    id: str
    course_id: str
    course_version: int = 1
    drill_focus: str | None = Field(default=None, max_length=500)
    status: DrillRunStatus
    questions: list[AdminDrillQuestionResponse]
    rubric_summary: list[str]
    share_url: str | None
    answer_count: int
    score_summary: DrillScoreSummary | None = None
    analysis_timeline: list[AnalysisTimelineItem] = Field(default_factory=list)
    can_analyze: bool
    error_message: str | None = None


class DrillAnswerAdminItem(ApiModel):
    id: str
    learner_name: str
    status: AnswerStatus
    total_score: int | None = None
    max_score: int | None = None
    answers: dict[str, str]
    grading_results: list[GradingResult] = Field(default_factory=list)


class DrillAnswersResponse(ApiModel):
    course_version: int
    answers: list[DrillAnswerAdminItem]


class LearnerDrillResponse(ApiModel):
    drill_run_id: str
    course_id: str
    questions: list[LearnerDrillQuestionResponse]


class CourseMetricsRun(ApiModel):
    drill_run_id: str
    course_version: int
    answer_count: int
    average_score: float | None = None
    max_score: int | None = None


class CourseMetricsResponse(ApiModel):
    course_id: str
    runs: list[CourseMetricsRun]


class DrillGenerationRequest(ApiModel):
    course_id: str | None = Field(default=None, exclude=True)
    course_title: str = Field(
        validation_alias=AliasChoices("courseTitle", "title"),
        serialization_alias="courseTitle",
    )
    course_markdown: str = Field(
        validation_alias=AliasChoices("courseMarkdown", "markdown"),
        serialization_alias="courseMarkdown",
    )
    drill_focus: str | None = Field(default=None, max_length=500)


class DrillGenerationResponse(ApiModel):
    questions: list[DrillQuestion] = Field(min_length=3, max_length=3)


class GradingRequest(ApiModel):
    question: DrillQuestion
    learner_answer: str = Field(
        validation_alias=AliasChoices("learnerAnswer", "answerText", "answer_text"),
        serialization_alias="learnerAnswer",
    )

    @property
    def answer_text(self) -> str:
        return self.learner_answer


class GradingResponse(GradingResult):
    pass


class FailureAnalysisRequest(ApiModel):
    course_markdown: str
    questions: list[DrillQuestion]
    answers: list[AnswerSubmission] = Field(min_length=1)
    grading_results: list[GradingResult]


class FailureAnalysisResponse(ApiModel):
    failure_signals: list[FailureSignal]
    perspectives: list[AnalysisPerspective] = Field(default_factory=list)
    review_notes: list[AnalysisReviewNote] = Field(default_factory=list)


class DocumentPatchRequest(ApiModel):
    course_id: str | None = Field(default=None, exclude=True)
    course_markdown: str = Field(
        validation_alias=AliasChoices("courseMarkdown", "baseMarkdown", "base_markdown"),
        serialization_alias="courseMarkdown",
    )
    failure_signals: list[FailureSignal]

    @property
    def base_markdown(self) -> str:
        return self.course_markdown


class DocumentPatchResponse(ApiModel):
    patched_markdown: str
    patch_summary: str
    risk_notes: list[str] = Field(default_factory=list)


class DrillGenerationStartResponse(ApiModel):
    drill_run_id: str
    share_url: str


class AnalysisStartResponse(ApiModel):
    patch_id: str
