import logging

from app.repositories.repositories import AnalysisExecutionRepository
from app.schemas import AnalysisClaim
from app.services.analysis_service import AnalysisService

logger = logging.getLogger("app.analysis")


class AutoAnalysisTrigger:
    """Best-effort automatic analysis started by a successful grading event."""

    def __init__(
        self,
        execution_repository: AnalysisExecutionRepository,
        analysis_service: AnalysisService,
    ) -> None:
        self._execution_repository = execution_repository
        self._analysis_service = analysis_service

    def maybe_run(self, drill_run_id: str) -> None:
        claim: AnalysisClaim | None = None
        try:
            claim = self._execution_repository.claim_auto_analysis(drill_run_id)
            if claim is None:
                logger.info(
                    "auto_analysis_skipped drill_run_id=%s reason=claim_not_acquired",
                    drill_run_id,
                )
                return

            self._log_claim_event("auto_analysis_started", claim)
            self._analysis_service.run_claimed_analysis(claim)
            self._log_claim_event("auto_analysis_completed", claim)
        except Exception as exc:
            if claim is None:
                logger.warning(
                    "auto_analysis_failed drill_run_id=%s error_type=%s",
                    drill_run_id,
                    type(exc).__name__,
                )
                return
            logger.warning(
                "auto_analysis_failed course_id=%s drill_run_id=%s origin=%s "
                "snapshot_agent_answer_count=%s snapshot_scored_answer_count=%s error_type=%s",
                claim.course_id,
                claim.drill_run_id,
                claim.origin.value,
                claim.snapshot_agent_answer_count,
                claim.snapshot_scored_answer_count,
                type(exc).__name__,
            )

    @staticmethod
    def _log_claim_event(event: str, claim: AnalysisClaim) -> None:
        logger.info(
            "%s course_id=%s drill_run_id=%s origin=%s snapshot_agent_answer_count=%s "
            "snapshot_scored_answer_count=%s",
            event,
            claim.course_id,
            claim.drill_run_id,
            claim.origin.value,
            claim.snapshot_agent_answer_count,
            claim.snapshot_scored_answer_count,
        )
