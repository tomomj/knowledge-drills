from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from google.adk.agents import Agent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import Field, PrivateAttr

from knowledge_drill_agent.failure_analysis_workflow import (
    ApprovedFindingsGate,
    FailureAnalysisApprovalError,
    ReviewLoopGate,
    ensure_partial_review_note,
)
from knowledge_drill_agent.samples import build_sample_failure_analysis_output
from knowledge_drill_agent.schemas import (
    CriticReviewOutput,
    EvidenceReviewOutput,
    FailureAnalysisOutput,
)


class _ScriptedStateAgent(BaseAgent):
    output_key: str
    outputs: list[object]
    calls: int = 0
    observed_critic_reviews: list[object] = Field(default_factory=list)

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        self.observed_critic_reviews.append(ctx.session.state.get("critic_review"))
        output = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={self.output_key: output}),
        )


class _FinalizerProbe(BaseAgent):
    calls: int = 0

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        self.calls += 1
        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    "finalizer_calls": self.calls,
                    "finalizer_approved_findings": ctx.session.state.get(
                        "approved_findings"
                    ),
                }
            ),
        )


class _FakeFinalizerLlm(BaseLlm):
    response_json: str
    _calls: int = PrivateAttr(default=0)

    @property
    def calls(self) -> int:
        return self._calls

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        self._calls += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=self.response_json)],
            )
        )


def _finding(
    finding_id: str = "finding-1",
    *,
    evidence: list[str] | None = None,
) -> dict[str, object]:
    return {
        "findingId": finding_id,
        "source": "misconception_analyst",
        "summary": "誤答傾向",
        "rationale": "採点結果に反復して現れる",
        "evidence": ["missingPoints: 手順"] if evidence is None else evidence,
    }


def _evidence_review(
    *,
    accepted: list[dict[str, object]] | None = None,
    rejected: list[dict[str, object]] | None = None,
    revision_notes: list[str] | None = None,
) -> dict[str, object]:
    return {
        "acceptedFindings": [_finding()] if accepted is None else accepted,
        "rejectedFindings": [] if rejected is None else rejected,
        "finalizerGuidance": ["承認対象だけを採用する"],
        "risks": [],
        "revisionNotes": [] if revision_notes is None else revision_notes,
    }


def _critic_review(
    verdict: str,
    approved_ids: list[str],
    *,
    issues: list[str] | None = None,
) -> dict[str, object]:
    return {
        "verdict": verdict,
        "issues": [] if issues is None else issues,
        "revisionInstructions": [] if issues is None else ["指摘を修正する"],
        "approvedFindingIds": approved_ids,
        "riskNotes": ["残存リスク"],
    }


def _build_workflow(
    evidence_outputs: list[object],
    critic_outputs: list[object],
) -> tuple[SequentialAgent, _ScriptedStateAgent, _ScriptedStateAgent, _FinalizerProbe]:
    evidence_agent = _ScriptedStateAgent(
        name="evidence_critic",
        output_key="evidence_review",
        outputs=evidence_outputs,
    )
    reviewer_agent = _ScriptedStateAgent(
        name="critic_reviewer",
        output_key="critic_review",
        outputs=critic_outputs,
    )
    review_loop = LoopAgent(
        name="review_loop",
        sub_agents=[evidence_agent, reviewer_agent, ReviewLoopGate()],
        max_iterations=3,
    )
    finalizer = _FinalizerProbe(name="finalizer")
    workflow = SequentialAgent(
        name="failure_analysis_test_workflow",
        sub_agents=[review_loop, ApprovedFindingsGate(), finalizer],
    )
    return workflow, evidence_agent, reviewer_agent, finalizer


async def _execute_workflow(workflow: SequentialAgent) -> dict[str, Any]:
    app_name = "failure_analysis_workflow_test"
    user_id = "test-user"
    session_id = "test-session"
    runner = InMemoryRunner(agent=workflow, app_name=app_name)
    await runner.session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    new_message = types.Content(role="user", parts=[types.Part(text="run")])
    async for _ in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=new_message,
    ):
        pass
    session = await runner.session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    assert session is not None
    return dict(session.state)


async def _execute_with_initial_state(
    workflow: SequentialAgent,
    initial_state: dict[str, object],
) -> tuple[dict[str, Any], list[Event]]:
    app_name = "failure_analysis_finalizer_test"
    user_id = "test-user"
    session_id = "test-session"
    runner = InMemoryRunner(agent=workflow, app_name=app_name)
    await runner.session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state=initial_state,
    )
    new_message = types.Content(role="user", parts=[types.Part(text="run")])
    events = [
        event
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message,
        )
    ]
    session = await runner.session_service.get_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    assert session is not None
    return dict(session.state), events


@pytest.mark.parametrize("encoding", ["model", "dict", "json"])
def test_first_valid_approval_exits_loop_and_runs_finalizer_once(encoding: str) -> None:
    evidence_model = EvidenceReviewOutput.model_validate(_evidence_review())
    critic_model = CriticReviewOutput.model_validate(
        _critic_review("approved", ["finding-1"])
    )
    if encoding == "model":
        evidence_output: object = evidence_model
        critic_output: object = critic_model
    elif encoding == "json":
        evidence_output = evidence_model.model_dump_json(by_alias=True)
        critic_output = critic_model.model_dump_json(by_alias=True)
    else:
        evidence_output = evidence_model.model_dump(by_alias=True)
        critic_output = critic_model.model_dump(by_alias=True)

    workflow, evidence_agent, reviewer_agent, finalizer = _build_workflow(
        [evidence_output],
        [critic_output],
    )
    state = asyncio.run(_execute_workflow(workflow))

    assert evidence_agent.calls == 1
    assert reviewer_agent.calls == 1
    assert finalizer.calls == 1
    assert state["review_termination_reason"] == "approved"
    assert state["finalizer_calls"] == 1
    assert [item["findingId"] for item in state["approved_findings"]] == [
        "finding-1"
    ]
    assert state["finalizer_approved_findings"] == state["approved_findings"]


def test_revision_cycle_reads_prior_review_and_records_revision_notes() -> None:
    first_review = _critic_review(
        "needs_revision",
        ["finding-1"],
        issues=["根拠を具体化する"],
    )
    workflow, evidence_agent, reviewer_agent, finalizer = _build_workflow(
        [
            _evidence_review(),
            _evidence_review(revision_notes=["根拠を questionId まで具体化した"]),
        ],
        [first_review, _critic_review("approved", ["finding-1"])],
    )

    state = asyncio.run(_execute_workflow(workflow))

    assert evidence_agent.calls == 2
    assert reviewer_agent.calls == 2
    assert evidence_agent.observed_critic_reviews[0] is None
    assert evidence_agent.observed_critic_reviews[1] == first_review
    assert state["evidence_review"]["revisionNotes"] == [
        "根拠を questionId まで具体化した"
    ]
    assert state["review_termination_reason"] == "approved"
    assert finalizer.calls == 1


def test_max_iterations_partially_adopts_only_valid_explicit_ids() -> None:
    workflow, evidence_agent, reviewer_agent, finalizer = _build_workflow(
        [_evidence_review()],
        [
            _critic_review(
                "needs_revision",
                ["finding-1"],
                issues=["追加根拠が必要"],
            )
        ],
    )

    state = asyncio.run(_execute_workflow(workflow))

    assert evidence_agent.calls == 3
    assert reviewer_agent.calls == 3
    assert finalizer.calls == 1
    assert state["review_termination_reason"] == "max_iterations_partial"
    assert [item["findingId"] for item in state["approved_findings"]] == [
        "finding-1"
    ]


def test_partial_finalizer_injects_complete_audit_note_once() -> None:
    model_output = build_sample_failure_analysis_output().model_copy(
        update={"review_notes": []}
    )
    fake_model = _FakeFinalizerLlm(
        model="fake-finalizer",
        response_json=model_output.model_dump_json(by_alias=True),
    )
    finalizer = Agent(
        name="failure_analysis_finalizer",
        model=fake_model,
        instruction="Return the final failure analysis JSON.",
        output_schema=FailureAnalysisOutput,
        after_model_callback=ensure_partial_review_note,
    )
    workflow = SequentialAgent(
        name="partial_finalizer_workflow",
        sub_agents=[ApprovedFindingsGate(), finalizer],
    )
    issues = ["教材根拠の追加確認が必要"]
    revision_instructions = ["次回は教材セクションを照合する"]
    risk_notes = ["設問品質が主因の可能性"]
    critic_review = {
        **_critic_review(
            "needs_revision",
            ["finding-1"],
            issues=issues,
        ),
        "revisionInstructions": revision_instructions,
        "riskNotes": risk_notes,
    }

    state, events = asyncio.run(
        _execute_with_initial_state(
            workflow,
            {
                "evidence_review": _evidence_review(),
                "critic_review": critic_review,
            },
        )
    )

    finalizer_events = [
        event
        for event in events
        if event.author == "failure_analysis_finalizer" and event.is_final_response()
    ]
    assert fake_model.calls == 1
    assert len(finalizer_events) == 1
    final_content = finalizer_events[0].content
    assert final_content is not None
    final_json = "".join(
        part.text or "" for part in (final_content.parts or []) if not part.thought
    )
    serialized_output = json.loads(final_json)
    assert "reviewNotes" in serialized_output
    assert "review_notes" not in serialized_output
    output = FailureAnalysisOutput.model_validate_json(final_json)
    partial_notes = [
        note for note in output.review_notes if note.id == "partial-adoption-audit"
    ]
    assert len(partial_notes) == 1
    assert partial_notes[0].source == "critic_reviewer"
    assert partial_notes[0].timeline_step == "decide_patch_strategy"
    assert partial_notes[0].evidence == [
        *(f"未解決事項: {issue}" for issue in issues),
        *(
            f"修正指示: {instruction}"
            for instruction in revision_instructions
        ),
        *(f"残存リスク: {risk}" for risk in risk_notes),
    ]
    assert state["review_termination_reason"] == "max_iterations_partial"


@pytest.mark.parametrize(
    "audit_override",
    [
        {"issues": []},
        {"issues": ["   "]},
        {"revisionInstructions": []},
        {"revisionInstructions": ["\t"]},
        {"riskNotes": []},
        {"riskNotes": ["\n"]},
    ],
    ids=[
        "missing-issues",
        "blank-issues",
        "missing-revision-instructions",
        "blank-revision-instructions",
        "missing-risk-notes",
        "blank-risk-notes",
    ],
)
def test_partial_adoption_requires_complete_nonblank_audit_context(
    audit_override: dict[str, object],
) -> None:
    critic_output = {
        **_critic_review(
            "needs_revision",
            ["finding-1"],
            issues=["追加根拠が必要"],
        ),
        **audit_override,
    }
    workflow, evidence_agent, reviewer_agent, finalizer = _build_workflow(
        [_evidence_review()],
        [critic_output],
    )

    with pytest.raises(FailureAnalysisApprovalError):
        asyncio.run(_execute_workflow(workflow))

    assert evidence_agent.calls == 3
    assert reviewer_agent.calls == 3
    assert finalizer.calls == 0


@pytest.mark.parametrize(
    ("evidence_output", "critic_output"),
    [
        (
            _evidence_review(),
            _critic_review("needs_revision", []),
        ),
        (
            _evidence_review(),
            _critic_review("approved", ["finding-1", "unknown-finding"]),
        ),
        (
            _evidence_review(),
            _critic_review("approved", ["finding-1", "finding-1"]),
        ),
        (
            _evidence_review(
                rejected=[_finding()],
            ),
            _critic_review("approved", ["finding-1"]),
        ),
        (
            _evidence_review(
                accepted=[_finding(), _finding()],
            ),
            _critic_review("approved", ["finding-1"]),
        ),
        (
            _evidence_review(
                accepted=[_finding(evidence=[])],
            ),
            _critic_review("approved", ["finding-1"]),
        ),
        (
            _evidence_review(),
            {
                **_critic_review("needs_revision", []),
                "issues": ["summary says finding-1 can be approved"],
            },
        ),
    ],
    ids=[
        "empty-selection",
        "mixed-valid-and-unknown-selection",
        "duplicate-approved-id",
        "accepted-rejected-conflict",
        "duplicate-accepted-id",
        "missing-accepted-evidence",
        "free-text-is-not-an-approval",
    ],
)
def test_invalid_or_unapproved_selection_fails_closed_before_finalizer(
    evidence_output: dict[str, object],
    critic_output: dict[str, object],
) -> None:
    workflow, evidence_agent, reviewer_agent, finalizer = _build_workflow(
        [evidence_output],
        [critic_output],
    )

    with pytest.raises(FailureAnalysisApprovalError):
        asyncio.run(_execute_workflow(workflow))

    assert evidence_agent.calls == 3
    assert reviewer_agent.calls == 3
    assert finalizer.calls == 0


def test_rejected_ids_must_be_unique() -> None:
    rejected = [_finding("rejected-1"), _finding("rejected-1")]
    workflow, evidence_agent, reviewer_agent, finalizer = _build_workflow(
        [_evidence_review(rejected=rejected)],
        [_critic_review("approved", ["finding-1"])],
    )

    with pytest.raises(FailureAnalysisApprovalError):
        asyncio.run(_execute_workflow(workflow))

    assert evidence_agent.calls == 3
    assert reviewer_agent.calls == 3
    assert finalizer.calls == 0


def test_json_payload_with_unapproved_free_text_is_not_inferred() -> None:
    evidence_json = json.dumps(_evidence_review(), ensure_ascii=False)
    critic_json = json.dumps(
        {
            **_critic_review("needs_revision", []),
            "issues": ["finding-1 は承認可能"],
        },
        ensure_ascii=False,
    )
    workflow, _, _, finalizer = _build_workflow(
        [evidence_json],
        [critic_json],
    )

    with pytest.raises(FailureAnalysisApprovalError):
        asyncio.run(_execute_workflow(workflow))

    assert finalizer.calls == 0
