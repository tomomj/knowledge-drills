from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, TypeVar

from google.adk.agents import BaseAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import BaseModel, ValidationError

from knowledge_drill_agent.schemas import (
    AnalysisReviewNote,
    CriticReviewOutput,
    EvidenceReviewOutput,
    FailureAnalysisOutput,
    ReviewedFinding,
)

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class FailureAnalysisApprovalError(RuntimeError):
    """Raised when the review loop has no structurally valid approved findings."""


@dataclass(frozen=True)
class _ValidatedReviewSelection:
    evidence_review: EvidenceReviewOutput
    critic_review: CriticReviewOutput
    approved_findings: tuple[ReviewedFinding, ...]


def _normalize_state_model(model: type[_ModelT], value: Any) -> _ModelT:
    if isinstance(value, model):
        return value
    if isinstance(value, str):
        return model.model_validate_json(value)
    return model.model_validate(value)


def _has_duplicate(values: list[str]) -> bool:
    return len(values) != len(set(values))


def _control_event(
    ctx: InvocationContext,
    *,
    author: str,
    actions: EventActions | None = None,
) -> Event:
    return Event(
        invocation_id=ctx.invocation_id,
        author=author,
        branch=ctx.branch,
        actions=actions or EventActions(),
    )


def _validate_partial_audit_context(critic_review: CriticReviewOutput) -> None:
    required_audit_fields = {
        "issues": critic_review.issues,
        "revision instructions": critic_review.revision_instructions,
        "risk notes": critic_review.risk_notes,
    }
    for field_name, values in required_audit_fields.items():
        if not values or any(not value.strip() for value in values):
            raise FailureAnalysisApprovalError(
                f"partial adoption requires non-empty {field_name}"
            )


def _validate_review_selection(
    state: dict[str, Any],
) -> _ValidatedReviewSelection:
    try:
        evidence_review = _normalize_state_model(
            EvidenceReviewOutput,
            state.get("evidence_review"),
        )
        critic_review = _normalize_state_model(
            CriticReviewOutput,
            state.get("critic_review"),
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise FailureAnalysisApprovalError(
            "failure analysis review state is missing or malformed"
        ) from exc

    accepted_ids = [finding.finding_id for finding in evidence_review.accepted_findings]
    rejected_ids = [finding.finding_id for finding in evidence_review.rejected_findings]
    approved_ids = critic_review.approved_finding_ids

    if any(not finding_id.strip() for finding_id in accepted_ids + rejected_ids):
        raise FailureAnalysisApprovalError("finding IDs must be non-empty")
    if _has_duplicate(accepted_ids) or _has_duplicate(rejected_ids):
        raise FailureAnalysisApprovalError("finding IDs must be unique within each list")

    accepted_id_set = set(accepted_ids)
    rejected_id_set = set(rejected_ids)
    if accepted_id_set & rejected_id_set:
        raise FailureAnalysisApprovalError(
            "accepted and rejected finding IDs must be disjoint"
        )

    for finding in evidence_review.accepted_findings:
        if not finding.source or not finding.evidence:
            raise FailureAnalysisApprovalError(
                "accepted findings require source and evidence"
            )
        if any(not item.strip() for item in finding.evidence):
            raise FailureAnalysisApprovalError(
                "accepted finding evidence must be non-empty"
            )

    if not approved_ids or any(not finding_id.strip() for finding_id in approved_ids):
        raise FailureAnalysisApprovalError(
            "approved finding IDs must be non-empty"
        )
    if _has_duplicate(approved_ids):
        raise FailureAnalysisApprovalError("approved finding IDs must be unique")

    approved_id_set = set(approved_ids)
    if not approved_id_set <= accepted_id_set:
        raise FailureAnalysisApprovalError(
            "approved finding IDs must refer only to accepted findings"
        )

    accepted_by_id = {
        finding.finding_id: finding for finding in evidence_review.accepted_findings
    }
    approved_findings = tuple(accepted_by_id[finding_id] for finding_id in approved_ids)
    return _ValidatedReviewSelection(
        evidence_review=evidence_review,
        critic_review=critic_review,
        approved_findings=approved_findings,
    )


class ReviewLoopGate(BaseAgent):
    """Exit the review loop only for an explicit, structurally valid approval."""

    def __init__(self, name: str = "review_gate") -> None:
        super().__init__(
            name=name,
            description="保存済み review を検証し、有効な承認だけで loop を終了する。",
        )

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        try:
            selection = _validate_review_selection(ctx.session.state)
        except FailureAnalysisApprovalError:
            yield _control_event(ctx, author=self.name)
            return

        if selection.critic_review.verdict == "approved":
            yield _control_event(
                ctx,
                author=self.name,
                actions=EventActions(escalate=True),
            )
            return

        yield _control_event(ctx, author=self.name)


class ApprovedFindingsGate(BaseAgent):
    """Persist only validated approved findings before final synthesis."""

    def __init__(self, name: str = "approved_findings_gate") -> None:
        super().__init__(
            name=name,
            description="loop 終了後に承認対象を再検証して finalizer 用 state を保存する。",
        )

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        selection = _validate_review_selection(ctx.session.state)
        if selection.critic_review.verdict == "needs_revision":
            _validate_partial_audit_context(selection.critic_review)
        termination_reason = (
            "approved"
            if selection.critic_review.verdict == "approved"
            else "max_iterations_partial"
        )
        approved_findings = [
            finding.model_dump(by_alias=True)
            for finding in selection.approved_findings
        ]
        yield _control_event(
            ctx,
            author=self.name,
            actions=EventActions(
                state_delta={
                    "approved_findings": approved_findings,
                    "review_termination_reason": termination_reason,
                }
            ),
        )


def ensure_partial_review_note(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None:
    """Inject a deterministic audit note into partial-adoption final output."""
    if callback_context.state.get("review_termination_reason") != (
        "max_iterations_partial"
    ):
        return None
    if llm_response.partial or not llm_response.content or not llm_response.content.parts:
        return None

    critic_review = _normalize_state_model(
        CriticReviewOutput,
        callback_context.state.get("critic_review"),
    )
    _validate_partial_audit_context(critic_review)

    response_text = "".join(
        part.text
        for part in llm_response.content.parts
        if part.text and not part.thought
    )
    output = FailureAnalysisOutput.model_validate_json(response_text)
    audit_note_id = "partial-adoption-audit"
    audit_note = AnalysisReviewNote(
        id=audit_note_id,
        source="critic_reviewer",
        timeline_step="decide_patch_strategy",
        title="反復上限での部分採用",
        summary=(
            "反復上限に達したため、明示的に承認された所見だけを部分採用しました。"
        ),
        evidence=[
            *(f"未解決事項: {issue}" for issue in critic_review.issues),
            *(
                f"修正指示: {instruction}"
                for instruction in critic_review.revision_instructions
            ),
            *(f"残存リスク: {risk}" for risk in critic_review.risk_notes),
        ],
    )
    review_notes = [
        note for note in output.review_notes if note.id != audit_note_id
    ]
    review_notes.append(audit_note)
    updated_output = output.model_copy(update={"review_notes": review_notes})
    updated_content = types.Content(
        role=llm_response.content.role,
        parts=[types.Part(text=updated_output.model_dump_json(by_alias=True))],
    )
    return llm_response.model_copy(update={"content": updated_content})
