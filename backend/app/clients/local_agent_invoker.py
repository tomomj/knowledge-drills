from typing import cast

from app.clients.agent_runtime_client import AgentPayload, AgentResponse


class LocalAgentInvoker:
    def __call__(self, task_name: str, payload: AgentPayload) -> AgentResponse:
        if task_name == "generate_drill":
            course_markdown = cast(str, payload["courseMarkdown"])
            drill_focus = payload.get("drillFocus")
            focus = drill_focus if isinstance(drill_focus, str) and drill_focus else None
            evidence = _source_evidence_from_markdown(course_markdown)
            return {
                "questions": [
                    _question("q1", evidence, focus),
                    _question("q2", evidence, focus),
                    _question("q3", evidence, focus),
                ]
            }
        if task_name == "grade_answer":
            question = cast(dict[str, object], payload["question"])
            max_score = int(cast(int, question.get("maxScore", 4)))
            return {
                "questionId": question["id"],
                "score": max(0, max_score - 1),
                "maxScore": max_score,
                "correctPoints": ["判断理由を示している"],
                "missingPoints": ["例外条件の説明を補える"],
                "feedback": "判断理由は示せています。例外条件も添えてください。",
                "failureTags": ["missing_exception"],
            }
        if task_name == "analyze_failures":
            answers = cast(list[object], payload["answers"])
            sample_size = len(answers)
            affected_count = max(1, sample_size - 1)
            return {
                "failureSignals": [
                    {
                        "id": "fs_local_001",
                        "title": "例外条件の説明不足",
                        "severity": "medium",
                        "evidence": ["例外条件への言及が不足している回答がある"],
                        "likelyCause": "資料内の例外条件が見つけにくい",
                        "suspectedDocumentGap": "判断基準に例外条件の説明が不足",
                        "targetSections": ["## 判断基準"],
                        "recommendedChange": "例外条件と確認先を追記する",
                        "affectedCount": affected_count,
                        "sampleSize": sample_size,
                        "confidenceNote": "少数回答の傾向です。",
                    }
                ],
                "reviewNotes": [
                    {
                        "id": "local-evidence-review",
                        "source": "evidence_critic",
                        "timelineStep": "match_course_evidence",
                        "title": "根拠照合",
                        "summary": "例外条件の不足を教材の判断基準と照合しました",
                        "evidence": ["## 判断基準"],
                    },
                    {
                        "id": "local-critic-review",
                        "source": "critic_reviewer",
                        "timelineStep": "decide_patch_strategy",
                        "title": "採用レビュー",
                        "summary": "承認済み所見のみを修正案に使います",
                        "evidence": ["approvedFindingIds: doc-gap-1"],
                    },
                ],
            }
        if task_name == "propose_document_patch":
            base_markdown = cast(str, payload["courseMarkdown"])
            return {
                "patchedMarkdown": f"{base_markdown}\n\n### 例外条件\n例外時は上長へ確認する。",
                "patchSummary": "例外条件と確認先を追記",
                "riskNotes": ["実際の運用ルールとの整合を確認してください。"],
            }
        raise RuntimeError(f"Unknown local agent task: {task_name}")


def _source_evidence_from_markdown(markdown: str) -> dict[str, str]:
    for line in markdown.splitlines():
        candidate = line.strip()
        if candidate.startswith("#"):
            return {
                "sectionHeading": candidate.lstrip("#").strip() or candidate,
                "excerpt": candidate,
            }

    for line in markdown.splitlines():
        candidate = line.strip()
        if candidate:
            return {"sectionHeading": "本文", "excerpt": candidate}

    return {"sectionHeading": "本文", "excerpt": markdown}


def _question(
    question_id: str,
    evidence: dict[str, str],
    drill_focus: str | None,
) -> dict[str, object]:
    focus_prefix = f"{drill_focus}について、" if drill_focus else ""
    return {
        "id": question_id,
        "question": (
            f"{question_id} の業務判断として、"
            f"{focus_prefix}講座の根拠に基づく対応と判断理由を書いてください。"
        ),
        "intent": (
            f"{drill_focus}に関する業務判断の根拠を確認する"
            if drill_focus
            else "業務判断の根拠を確認する"
        ),
        "rubric": [{"criterion": "根拠と例外条件", "points": 4, "required": True}],
        "idealAnswer": f"講座の根拠「{evidence['excerpt']}」に基づいて判断する。",
        "sourceEvidence": [evidence],
        "maxScore": 4,
    }
