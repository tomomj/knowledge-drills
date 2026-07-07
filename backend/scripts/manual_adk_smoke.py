from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.clients.adk_agent_invoker import AdkAgentConfigurationError, create_adk_invoker
from app.clients.agent_runtime_client import AgentRuntimeClient
from app.config import Settings
from app.schemas import (
    AnswerStatus,
    AnswerSubmission,
    DocumentPatchRequest,
    DrillGenerationRequest,
    FailureAnalysisRequest,
    GradingRequest,
)

COURSE_TITLE = "Incident response basics"
COURSE_MARKDOWN = """# Incident response basics

## Triage
Confirm user impact, affected systems, and the current severity before changing state.

## Escalation
Escalate to the incident commander when customer impact is confirmed or severity is unclear.

## Communication
Post concise updates that state impact, mitigation, next owner, and next update time.
"""
LEARNER_ANSWER = (
    "I would check the affected system and tell the team. "
    "I would also mention the next update time."
)


def run_smoke() -> dict[str, object]:
    settings = Settings(agent_mode="adk")
    client = AgentRuntimeClient(invoker=create_adk_invoker(settings))

    drill = client.generate_drill(
        DrillGenerationRequest(
            course_title=COURSE_TITLE,
            course_markdown=COURSE_MARKDOWN,
        )
    )
    question = drill.questions[0]
    grading = client.grade_answer(
        GradingRequest(
            question=question,
            learner_answer=LEARNER_ANSWER,
        )
    )
    answer = AnswerSubmission(
        id="manual-smoke-answer-1",
        drill_run_id="manual-smoke-drill-1",
        learner_name="manual-smoke",
        status=AnswerStatus.GRADED,
        answers={question.id: LEARNER_ANSWER},
        grading_results=[grading],
        total_score=grading.score,
        max_score=grading.max_score,
    )
    analysis = client.analyze_failures(
        FailureAnalysisRequest(
            course_markdown=COURSE_MARKDOWN,
            questions=drill.questions,
            answers=[answer],
            grading_results=[grading],
        )
    )
    patch = client.propose_document_patch(
        DocumentPatchRequest(
            course_markdown=COURSE_MARKDOWN,
            failure_signals=analysis.failure_signals,
        )
    )

    return {
        "ranAt": datetime.now(UTC).isoformat(),
        "agentMode": "adk",
        "model": os.getenv("KNOWLEDGE_DRILL_AGENT_MODEL", "gemini-2.5-flash"),
        "operations": {
            "generateDrill": {
                "questionCount": len(drill.questions),
                "firstQuestionId": question.id,
            },
            "gradeAnswer": {
                "questionId": grading.question_id,
                "score": grading.score,
                "maxScore": grading.max_score,
            },
            "analyzeFailures": {
                "failureSignalCount": len(analysis.failure_signals),
            },
            "proposeDocumentPatch": {
                "patchSummary": patch.patch_summary,
                "riskNoteCount": len(patch.risk_notes),
            },
        },
        "responses": {
            "drill": drill.model_dump(mode="json", by_alias=True),
            "grading": grading.model_dump(mode="json", by_alias=True),
            "analysis": analysis.model_dump(mode="json", by_alias=True),
            "patch": patch.model_dump(mode="json", by_alias=True),
        },
    }


def default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("manual-smoke-results") / f"adk_smoke_{timestamp}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one real Gemini-backed ADK smoke cycle for Knowledge Drills.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output_path(),
        help="JSON file path for the smoke result.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_smoke()
    except AdkAgentConfigurationError as exc:
        print(f"ADK configuration error: {exc}", file=sys.stderr)
        return 2

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote smoke result: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
