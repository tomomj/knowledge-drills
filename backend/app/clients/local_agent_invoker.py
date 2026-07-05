from typing import cast

from app.clients.agent_runtime_client import AgentPayload, AgentResponse


class LocalAgentInvoker:
    def __call__(self, task_name: str, payload: AgentPayload) -> AgentResponse:
        if task_name == "generate_drill":
            return {"questions": [_question("q1"), _question("q2"), _question("q3")]}
        if task_name == "grade_answer":
            question = cast(dict[str, object], payload["question"])
            return {
                "questionId": question["id"],
                "score": 3,
                "maxScore": 4,
                "correctPoints": ["判断理由を示している"],
                "missingPoints": ["例外条件の説明を補える"],
                "feedback": "判断理由は示せています。例外条件も添えてください。",
                "failureTags": ["missing_exception"],
            }
        if task_name == "analyze_failures":
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
                        "sampleSize": 1,
                        "confidenceNote": "少数回答の傾向です。",
                    }
                ]
            }
        if task_name == "propose_document_patch":
            base_markdown = cast(str, payload["courseMarkdown"])
            return {
                "patchedMarkdown": f"{base_markdown}\n\n### 例外条件\n例外時は上長へ確認する。",
                "patchSummary": "例外条件と確認先を追記",
                "riskNotes": ["実際の運用ルールとの整合を確認してください。"],
            }
        raise RuntimeError(f"Unknown local agent task: {task_name}")


def _question(question_id: str) -> dict[str, object]:
    return {
        "id": question_id,
        "question": f"{question_id} の業務判断について、根拠と例外条件を書いてください。",
        "intent": "業務判断の根拠を確認する",
        "rubric": [{"criterion": "根拠と例外条件", "points": 4, "required": True}],
        "idealAnswer": "資料の判断基準を根拠にし、例外時の確認先も述べる。",
        "sourceEvidence": [
            {
                "sectionHeading": "判断基準",
                "excerpt": "## 判断基準",
            }
        ],
        "maxScore": 4,
    }
