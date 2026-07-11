import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import uuid4

from app.clients.agent_runtime_client import AgentRuntimeClient
from app.errors import AppError
from app.repositories.repositories import (
    AnalysisExecutionRepository,
    AnswerRepository,
    CourseRepository,
    DrillRepository,
    PatchRepository,
)
from app.schemas import (
    AnalysisClaim,
    AnalysisReviewTimelineStep,
    AnalysisStepStatus,
    AnalysisTimelineItem,
    AnswerStatus,
    AnswerSubmission,
    Course,
    DocumentPatch,
    DocumentPatchRequest,
    DrillRun,
    DrillRunStatus,
    FailureAnalysisRequest,
    FailureAnalysisResponse,
    PatchStatus,
)
from app.utils.diff import build_unified_diff

logger = logging.getLogger("app.analysis")

ANALYSIS_FAILED_MESSAGE = "analysis failed"
PATCH_SKIPPED_MESSAGE = "承認された Failure Signal がないため patch 提案を見送りました"
ANALYSIS_STEPS: tuple[tuple[str, str], ...] = (
    ("collect_answers", "回答データを収集"),
    ("detect_failure_patterns", "つまずき箇所を特定"),
    ("match_course_evidence", "教材の根拠を照合"),
    ("decide_patch_strategy", "改善方針を判断"),
    ("create_patch", "修正案を作成"),
)


class AnalysisService:
    def __init__(
        self,
        drill_repository: DrillRepository,
        answer_repository: AnswerRepository,
        *,
        course_repository: CourseRepository | None = None,
        patch_repository: PatchRepository | None = None,
        agent_client: AgentRuntimeClient | None = None,
        execution_repository: AnalysisExecutionRepository | None = None,
    ) -> None:
        self._drill_repository = drill_repository
        self._answer_repository = answer_repository
        self._course_repository = course_repository
        self._patch_repository = patch_repository
        self._agent_client = agent_client
        self._execution_repository = execution_repository

    def start_analysis(self, drill_run_id: str, owner_user_id: str | None = None) -> DrillRun:
        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
        if owner_user_id is not None:
            self._ensure_drill_owned_by(drill_run, owner_user_id)
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

        answers = self._answer_repository.list_by_drill_run(drill_run.id)
        graded_answers = [answer for answer in answers if answer.status == AnswerStatus.GRADED]
        if not graded_answers:
            raise AppError("no_graded_answers", "At least one graded answer is required.")

        analyzing = drill_run.model_copy(
            update={
                "status": DrillRunStatus.ANALYZING,
                "error_message": None,
                "analysis_timeline": _initial_timeline("collect_answers"),
            }
        )
        self._drill_repository.update(analyzing)
        if self._course_repository is not None:
            self._course_repository.update_summary(
                drill_run.course_id,
                latest_drill_run_id=drill_run.id,
                latest_drill_status=analyzing.status,
                answer_count=len(answers),
            )
        return analyzing

    def generate_patch_proposal(
        self,
        drill_run_id: str,
        owner_user_id: str | None = None,
    ) -> DocumentPatch | None:
        if self._course_repository is None or self._agent_client is None:
            raise RuntimeError("AnalysisService dependencies are not configured")

        drill_run = self._drill_repository.get(drill_run_id)
        if drill_run is None:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
        course = self._course_repository.get(drill_run.course_id)
        if course is None:
            if owner_user_id is None:
                raise AppError("course_not_found", "Course was not found.", status_code=404)
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)
        if owner_user_id is not None and course.owner_user_id != owner_user_id:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)

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
        if not failure_analysis.failure_signals:
            logger.info(
                "patch proposal skipped course_id=%s drill_run_id=%s "
                "reason=no_approved_failure_signals",
                course.id,
                drill_run.id,
            )
            return None
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

    def run_analysis(self, drill_run_id: str, owner_user_id: str) -> DocumentPatch | None:
        if self._execution_repository is not None:
            claim = self._execution_repository.claim_manual_analysis(
                drill_run_id,
                owner_user_id,
            )
            return self.run_claimed_analysis(claim)

        if self._course_repository is None or self._patch_repository is None:
            raise RuntimeError("AnalysisService dependencies are not configured")

        drill_run = self.start_analysis(drill_run_id, owner_user_id)
        try:
            patch, drill_run, analyzed_answer_count = self._generate_patch_proposal_with_timeline(
                drill_run,
                owner_user_id,
            )
        except Exception as exc:
            latest_drill_run = self._drill_repository.get(drill_run.id) or drill_run
            running_step_id = _running_step_id(latest_drill_run.analysis_timeline)
            logger.warning(
                "analysis failed course_id=%s drill_run_id=%s step=%s error_type=%s",
                latest_drill_run.course_id,
                latest_drill_run.id,
                running_step_id or "unknown",
                type(exc).__name__,
            )
            failed_timeline = _fail_running_step(latest_drill_run.analysis_timeline)
            failed = drill_run.model_copy(
                update={
                    "status": DrillRunStatus.READY,
                    "error_message": ANALYSIS_FAILED_MESSAGE,
                    "analysis_timeline": failed_timeline,
                }
            )
            self._drill_repository.update(failed)
            self._course_repository.update_summary(
                failed.course_id,
                latest_drill_run_id=failed.id,
                latest_drill_status=failed.status,
            )
            raise

        if patch is not None:
            self._patch_repository.create(patch)
        analyzed = drill_run.model_copy(
            update={
                "status": DrillRunStatus.ANALYZED,
                "analyzed_answer_count": analyzed_answer_count,
            }
        )
        self._drill_repository.update(analyzed)
        course = self._course_repository.get(drill_run.course_id)
        if course is None:
            raise AppError("course_not_found", "Course was not found.", status_code=404)
        self._course_repository.update_summary(
            course.id,
            latest_drill_run_id=drill_run.id,
            latest_drill_status=analyzed.status,
            latest_patch_id=patch.id if patch is not None else None,
            latest_patch_status=patch.status if patch is not None else None,
        )
        return patch

    def run_claimed_analysis(self, claim: AnalysisClaim) -> DocumentPatch | None:
        if (
            self._course_repository is None
            or self._agent_client is None
            or self._execution_repository is None
        ):
            raise RuntimeError("AnalysisService dependencies are not configured")
        execution_repository = self._execution_repository

        try:
            drill_run = self._drill_repository.get(claim.drill_run_id)
            course = self._course_repository.get(claim.course_id)
            if (
                drill_run is None
                or drill_run.course_id != claim.course_id
                or course is None
                or course.owner_user_id != claim.owner_user_id
            ):
                raise AppError(
                    "analysis_snapshot_invalid",
                    "Analysis snapshot no longer matches its course and drill.",
                    status_code=409,
                )

            answers = self._load_claimed_answers(claim)
            patch, timeline = self._execute_analysis_with_timeline(
                drill_run,
                course,
                answers,
                observed_answer_count=claim.snapshot_agent_answer_count,
                persist_progress=lambda progress: execution_repository.update_progress(
                    claim,
                    progress,
                ),
            )
        except Exception as exc:
            latest_drill_run = self._drill_repository.get(claim.drill_run_id)
            timeline = _fail_running_step(
                latest_drill_run.analysis_timeline
                if latest_drill_run is not None
                else _initial_timeline("collect_answers")
            )
            logger.warning(
                "analysis failed course_id=%s drill_run_id=%s step=%s error_type=%s",
                claim.course_id,
                claim.drill_run_id,
                _failed_step_id(timeline) or "unknown",
                type(exc).__name__,
            )
            try:
                execution_repository.fail_analysis(
                    claim,
                    timeline,
                    ANALYSIS_FAILED_MESSAGE,
                )
            except Exception:
                logger.exception(
                    "analysis failure terminal failed course_id=%s drill_run_id=%s",
                    claim.course_id,
                    claim.drill_run_id,
                )
            raise

        try:
            return execution_repository.complete_analysis(claim, timeline, patch)
        except AppError as exc:
            if exc.code == "analysis_course_version_changed":
                raise
            logger.exception(
                "analysis completion persistence failed course_id=%s drill_run_id=%s "
                "error_type=%s",
                claim.course_id,
                claim.drill_run_id,
                type(exc).__name__,
            )
            raise
        except Exception as exc:
            logger.exception(
                "analysis completion persistence failed course_id=%s drill_run_id=%s "
                "error_type=%s",
                claim.course_id,
                claim.drill_run_id,
                type(exc).__name__,
            )
            raise

    def _load_claimed_answers(self, claim: AnalysisClaim) -> list[AnswerSubmission]:
        answers: list[AnswerSubmission] = []
        for answer_id in claim.answer_ids:
            answer = self._answer_repository.get(answer_id)
            if (
                answer is None
                or answer.drill_run_id != claim.drill_run_id
                or answer.status is not AnswerStatus.GRADED
            ):
                raise AppError(
                    "analysis_snapshot_invalid",
                    "A claimed answer is missing or no longer matches the analysis snapshot.",
                    status_code=409,
                )
            answers.append(answer)
        if len(answers) != claim.snapshot_agent_answer_count:
            raise AppError(
                "analysis_snapshot_invalid",
                "The claimed answer count does not match the analysis snapshot.",
                status_code=409,
            )
        return answers

    def _generate_patch_proposal_with_timeline(
        self,
        drill_run: DrillRun,
        owner_user_id: str,
    ) -> tuple[DocumentPatch | None, DrillRun, int]:
        if self._course_repository is None or self._agent_client is None:
            raise RuntimeError("AnalysisService dependencies are not configured")

        course = self._course_repository.get(drill_run.course_id)
        if course is None or course.owner_user_id != owner_user_id:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)

        answers = self._answer_repository.list_by_drill_run(drill_run.id)
        graded_answers = [answer for answer in answers if answer.status == AnswerStatus.GRADED]
        if not graded_answers:
            raise AppError("no_graded_answers", "At least one graded answer is required.")
        analyzed_answer_count = len(graded_answers)

        patch, timeline = self._execute_analysis_with_timeline(
            drill_run,
            course,
            graded_answers,
            observed_answer_count=len(answers),
            persist_progress=lambda progress: self._drill_repository.update(
                drill_run.model_copy(update={"analysis_timeline": progress})
            ),
        )
        return (
            patch,
            drill_run.model_copy(update={"analysis_timeline": timeline}),
            analyzed_answer_count,
        )

    def _execute_analysis_with_timeline(
        self,
        drill_run: DrillRun,
        course: Course,
        answers: list[AnswerSubmission],
        *,
        observed_answer_count: int,
        persist_progress: Callable[[list[AnalysisTimelineItem]], None],
    ) -> tuple[DocumentPatch | None, list[AnalysisTimelineItem]]:
        if self._agent_client is None:
            raise RuntimeError("AnalysisService dependencies are not configured")

        timeline = drill_run.analysis_timeline or _initial_timeline("collect_answers")

        def update(
            step_id: str,
            status: AnalysisStepStatus,
            *,
            summary: str | None = None,
            evidence: list[str] | None = None,
        ) -> None:
            nonlocal timeline
            timeline = _replace_timeline_item(
                timeline,
                step_id,
                status,
                summary=summary,
                evidence=evidence,
            )
            persist_progress(timeline)

        answer_count = len(answers)
        update(
            "collect_answers",
            AnalysisStepStatus.COMPLETED,
            summary=f"採点済み回答 {answer_count} 件を収集しました",
            evidence=[
                f"回答総数 {observed_answer_count} 件",
                f"採点済み {answer_count} 件",
            ],
        )
        update(
            "detect_failure_patterns",
            AnalysisStepStatus.RUNNING,
            summary="採点結果から繰り返し発生するつまずきを抽出しています",
        )
        failure_analysis = self._agent_client.analyze_failures(
            FailureAnalysisRequest(
                course_markdown=course.markdown,
                questions=drill_run.questions,
                answers=answers,
                grading_results=[
                    result for answer in answers for result in answer.grading_results
                ],
            )
        )
        update(
            "detect_failure_patterns",
            AnalysisStepStatus.COMPLETED,
            summary=f"Failure Signal {len(failure_analysis.failure_signals)} 件を特定しました",
            evidence=_failure_pattern_evidence(failure_analysis),
        )

        target_sections = _unique_strings(
            section
            for signal in failure_analysis.failure_signals
            for section in signal.target_sections
        )
        update(
            "match_course_evidence",
            AnalysisStepStatus.COMPLETED,
            summary=f"対象セクション {len(target_sections)} 件を照合しました",
            evidence=_merge_timeline_evidence(
                _review_note_evidence(
                    failure_analysis,
                    AnalysisReviewTimelineStep.MATCH_COURSE_EVIDENCE,
                ),
                target_sections,
            ),
        )

        recommended_changes = _unique_strings(
            signal.recommended_change for signal in failure_analysis.failure_signals
        )
        patch_skipped = not failure_analysis.failure_signals
        update(
            "decide_patch_strategy",
            AnalysisStepStatus.COMPLETED,
            summary=(
                "承認された所見がないため patch 見送りを判断しました"
                if patch_skipped
                else "教材修正方針を選定しました"
            ),
            evidence=_merge_timeline_evidence(
                _review_note_evidence(
                    failure_analysis,
                    AnalysisReviewTimelineStep.DECIDE_PATCH_STRATEGY,
                ),
                recommended_changes,
            ),
        )

        if patch_skipped:
            update(
                "create_patch",
                AnalysisStepStatus.SKIPPED,
                summary=PATCH_SKIPPED_MESSAGE,
            )
            logger.info(
                "patch proposal skipped course_id=%s drill_run_id=%s "
                "reason=no_approved_failure_signals",
                course.id,
                drill_run.id,
            )
            return None, timeline

        update(
            "create_patch",
            AnalysisStepStatus.RUNNING,
            summary="Markdown patch 案を作成しています",
        )
        patch_response = self._agent_client.propose_document_patch(
            DocumentPatchRequest(
                course_markdown=course.markdown,
                failure_signals=failure_analysis.failure_signals,
            )
        )
        update(
            "create_patch",
            AnalysisStepStatus.COMPLETED,
            summary=patch_response.patch_summary,
            evidence=patch_response.risk_notes[:3],
        )

        patch = DocumentPatch(
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
            analysis_timeline=timeline,
        )
        return patch, timeline

    def _ensure_drill_owned_by(self, drill_run: DrillRun, owner_user_id: str) -> None:
        if self._course_repository is None:
            raise RuntimeError("AnalysisService dependencies are not configured")
        course = self._course_repository.get(drill_run.course_id)
        if course is None or course.owner_user_id != owner_user_id:
            raise AppError("drill_run_not_found", "Drill run was not found.", status_code=404)


def _initial_timeline(running_step_id: str) -> list[AnalysisTimelineItem]:
    return [
        AnalysisTimelineItem(
            id=step_id,
            title=title,
            status=(
                AnalysisStepStatus.RUNNING
                if step_id == running_step_id
                else AnalysisStepStatus.PENDING
            ),
        )
        for step_id, title in ANALYSIS_STEPS
    ]


def _replace_timeline_item(
    timeline: list[AnalysisTimelineItem],
    step_id: str,
    status: AnalysisStepStatus,
    *,
    summary: str | None,
    evidence: list[str] | None,
) -> list[AnalysisTimelineItem]:
    if not timeline:
        timeline = _initial_timeline(step_id)
    completed_at = (
        _utc_now() if status in {AnalysisStepStatus.COMPLETED, AnalysisStepStatus.FAILED} else None
    )
    return [
        item.model_copy(
            update={
                "status": status,
                "summary": summary,
                "evidence": evidence or [],
                "completed_at": completed_at,
            }
        )
        if item.id == step_id
        else item
        for item in timeline
    ]


def _fail_running_step(timeline: list[AnalysisTimelineItem]) -> list[AnalysisTimelineItem]:
    for item in timeline:
        if item.status == AnalysisStepStatus.RUNNING:
            return _replace_timeline_item(
                timeline,
                item.id,
                AnalysisStepStatus.FAILED,
                summary=ANALYSIS_FAILED_MESSAGE,
                evidence=[],
            )
    return timeline


def _running_step_id(timeline: list[AnalysisTimelineItem]) -> str | None:
    for item in timeline:
        if item.status == AnalysisStepStatus.RUNNING:
            return item.id
    return None


def _failed_step_id(timeline: list[AnalysisTimelineItem]) -> str | None:
    for item in timeline:
        if item.status == AnalysisStepStatus.FAILED:
            return item.id
    return None


def _unique_strings(values: Iterable[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if isinstance(value, str) and value not in unique:
            unique.append(value)
    return unique


def _failure_pattern_evidence(failure_analysis: FailureAnalysisResponse) -> list[str]:
    perspective_evidence: list[str] = []
    for perspective in failure_analysis.perspectives:
        title = " ".join((perspective.title or perspective.id).split())
        summary = " ".join(perspective.summary.split())
        if not title or not summary:
            continue
        perspective_evidence.append(f"{title}: {summary}")
        if len(perspective_evidence) == 3:
            break
    existing_evidence = (
        perspective_evidence
        if perspective_evidence
        else [signal.title for signal in failure_analysis.failure_signals]
    )
    return _merge_timeline_evidence(
        _review_note_evidence(
            failure_analysis,
            AnalysisReviewTimelineStep.DETECT_FAILURE_PATTERNS,
        ),
        existing_evidence,
    )


def _review_note_evidence(
    failure_analysis: FailureAnalysisResponse,
    timeline_step: AnalysisReviewTimelineStep,
) -> list[str]:
    evidence: list[str] = []
    for note in failure_analysis.review_notes:
        if note.timeline_step != timeline_step:
            continue
        title = " ".join((note.title or note.id).split())
        summary = " ".join(note.summary.split())
        if not title or not summary:
            continue
        first_evidence = next(
            (" ".join(item.split()) for item in note.evidence if item.strip()),
            "",
        )
        formatted = f"{title}: {summary}"
        if first_evidence:
            formatted = f"{formatted} ({first_evidence})"
        evidence.append(formatted)
    return evidence


def _merge_timeline_evidence(
    review_evidence: Iterable[str],
    existing_evidence: Iterable[str],
) -> list[str]:
    return _unique_strings([*review_evidence, *existing_evidence])[:3]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
