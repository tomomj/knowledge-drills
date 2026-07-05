from knowledge_drill_agent.schemas import (
    DocumentPatchOutput,
    DrillGenerationOutput,
    DrillQuestion,
    FailureAnalysisOutput,
    FailureSignal,
    GradingOutput,
    RubricItem,
    SourceEvidence,
)


def build_sample_drill_generation_output() -> DrillGenerationOutput:
    questions = [
        DrillQuestion(
            id=f"q{index}",
            question=f"講座の方針に基づき、ケース {index} の判断理由を書いてください。",
            intent="受講者が実務判断を根拠付きで説明できるかを確認する。",
            rubric=[
                RubricItem(criterion="講座内の根拠を示している", points=2, required=True),
                RubricItem(criterion="判断理由を具体的に説明している", points=2, required=True),
            ],
            ideal_answer="講座内の根拠を引用し、条件に応じた判断理由を説明する。",
            source_evidence=[SourceEvidence(section_heading="対応方針", excerpt="## 対応方針")],
            max_score=4,
        )
        for index in range(1, 4)
    ]
    return DrillGenerationOutput(questions=questions)


def build_sample_grading_output() -> GradingOutput:
    return GradingOutput(
        question_id="q1",
        score=2,
        max_score=4,
        correct_points=["判断の方向性は講座内容と一致している"],
        missing_points=["判断理由の根拠が明示されていない"],
        feedback="講座内の該当箇所を根拠として添えると、判断理由が明確になります。",
        failure_tags=["missing_evidence"],
    )


def build_sample_failure_analysis_output() -> FailureAnalysisOutput:
    return FailureAnalysisOutput(
        failure_signals=[
            FailureSignal(
                id="fs_sample_001",
                title="判断根拠の不足",
                severity="medium",
                evidence=["2 件の回答で根拠箇所への言及がなかった"],
                likely_cause="例外条件を判断する説明が講座内で短い",
                suspected_document_gap="判断基準の具体例が不足している",
                target_sections=["## 対応方針"],
                recommended_change="例外条件の判断例を 1 つ追加する",
                sample_size=2,
                confidence_note="少数回答に基づく傾向として扱う",
            )
        ]
    )


def build_sample_document_patch_output() -> DocumentPatchOutput:
    return DocumentPatchOutput(
        patched_markdown="# 講座\n\n## 対応方針\n例外条件では根拠を確認して判断する。\n",
        patch_summary="対応方針に例外条件の判断例を追加した。",
        risk_notes=["少数回答に基づくため、講座オーナーの確認が必要。"],
    )
