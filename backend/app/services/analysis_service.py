from uuid import uuid4

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.errors import AppError
from app.repositories.repositories import (
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
)
from app.schemas import (
    AnswerStatus,
    DocumentPatch,
    DocumentPatchRequest,
    DrillRun,
    DrillRunStatus,
    FailureAnalysisRequest,
    PatchStatus,
)
from app.utils.diff import build_unified_diff

ANALYSIS_FAILED_MESSAGE = "analysis failed"


class AnalysisService:
    def __init__(
        self,
        drill_repository: DrillRepository,
        answer_repository: AnswerRepository,
        *,
        course_repository: CourseRepository | None = None,
        patch_repository: PatchRepository | None = None,
        agent_client: AgentRuntimeClient | None = None,
    ) -> None:
        self._drill_repository = drill_repository
        self._answer_repository = answer_repository
        self._course_repository = course_repository
        self._patch_repository = patch_repository
        self._agent_client = agent_client

    def start_analysis(self, drill_run_id: str) -> DrillRun:
        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
        if (
            drill_run.status == DrillRunStatus.FAILED
            and drill_run.error_message != ANALYSIS_FAILED_MESSAGE
        ):
            raise AppError("drill_not_analyzable", "Drill run is not analyzable.", status_code=409)
        if drill_run.status not in {
            DrillRunStatus.READY,
            DrillRunStatus.ANALYZED,
            DrillRunStatus.FAILED,
        }:
            raise AppError("drill_not_analyzable", "Drill run is not analyzable.", status_code=409)

        graded_answers = [
            answer
            for answer in self._answer_repository.list_by_drill_run(drill_run.id)
            if answer.status == AnswerStatus.GRADED
        ]
        if not graded_answers:
            raise AppError("no_graded_answers", "At least one graded answer is required.")

        analyzing = drill_run.model_copy(
            update={"status": DrillRunStatus.ANALYZING, "error_message": None}
        )
        self._drill_repository.update(analyzing)
        return analyzing

    def generate_patch_proposal(self, drill_run_id: str) -> DocumentPatch:
        if self._course_repository is None or self._agent_client is None:
            raise RuntimeError("AnalysisService dependencies are not configured")

        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
        course = self._course_repository.get(drill_run.course_id)
        if course is None:
            raise AppError("course_not_found", "Course was not found.", status_code=404)

        graded_answers = [
            answer
            for answer in self._answer_repository.list_by_drill_run(drill_run.id)
            if answer.status == AnswerStatus.GRADED
        ]
        if not graded_answers:
            raise AppError("no_graded_answers", "At least one graded answer is required.")

        failure_analysis = self._agent_client.analyze_failures(
            FailureAnalysisRequest(
                course_markdown=course.markdown,
                questions=drill_run.questions,
                answers=graded_answers,
                grading_results=[
                    result for answer in graded_answers for result in answer.grading_results
                ],
            )
        )
        patch_response = self._agent_client.propose_document_patch(
            DocumentPatchRequest(
                course_markdown=course.markdown,
                failure_signals=failure_analysis.failure_signals,
            )
        )
        return DocumentPatch(
            id=uuid4().hex,
            course_id=course.id,
            drill_run_id=drill_run.id,
            status=PatchStatus.PROPOSED,
            base_markdown=course.markdown,
            patched_markdown=patch_response.patched_markdown,
            patch_summary=patch_response.patch_summary,
            risk_notes=patch_response.risk_notes,
            diff_text=build_unified_diff(course.markdown, patch_response.patched_markdown),
            failure_signals=failure_analysis.failure_signals,
        )

    def run_analysis(self, drill_run_id: str) -> DocumentPatch:
        if self._course_repository is None or self._patch_repository is None:
            raise RuntimeError("AnalysisService dependencies are not configured")

        drill_run = self.start_analysis(drill_run_id)
        try:
            patch = self.generate_patch_proposal(drill_run.id)
        except Exception:
            failed = drill_run.model_copy(
                update={
                    "status": DrillRunStatus.FAILED,
                    "error_message": ANALYSIS_FAILED_MESSAGE,
                }
            )
            self._drill_repository.update(failed)
            raise

        self._patch_repository.create(patch)
        analyzed = drill_run.model_copy(update={"status": DrillRunStatus.ANALYZED})
        self._drill_repository.update(analyzed)
        course = self._course_repository.get(drill_run.course_id)
        if course is None:
            raise AppError("course_not_found", "Course was not found.", status_code=404)
        self._course_repository.update(
            course.model_copy(
                update={
                    "latest_patch_id": patch.id,
                    "latest_drill_run_id": drill_run.id,
                }
            )
        )
        return patch
