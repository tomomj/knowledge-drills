from __future__ import annotations

from dataclasses import dataclass

from app.schemas import (
    AnalysisStepStatus,
    AnalysisTimelineItem,
    CourseScoreTrendPoint,
    DrillQuestion,
    DrillRunStatus,
    FailureSeverity,
    FailureSignal,
    GradingResult,
    RubricItem,
    SourceEvidence,
)


@dataclass(frozen=True)
class DemoAnswerDefinition:
    id_suffix: str
    learner_name: str
    answers_by_question: tuple[tuple[str, str], ...]
    total_score: int
    grading_results: tuple[GradingResult, ...]


@dataclass(frozen=True)
class DemoDrillDefinition:
    id_suffix: str
    share_token_suffix: str
    course_version: int
    status: DrillRunStatus
    questions: tuple[DrillQuestion, ...]
    answers: tuple[DemoAnswerDefinition, ...]
    analysis_timeline: tuple[AnalysisTimelineItem, ...] = ()


@dataclass(frozen=True)
class DemoPatchDefinition:
    id_suffix: str
    drill_id_suffix: str
    base_markdown: str
    patched_markdown: str
    patch_summary: str
    risk_notes: tuple[str, ...]
    failure_signals: tuple[FailureSignal, ...]
    analysis_timeline: tuple[AnalysisTimelineItem, ...]


@dataclass(frozen=True)
class DemoCourseDefinition:
    slug: str
    title: str
    drill_focus: str
    markdown_versions: tuple[str, ...]
    score_trend: tuple[CourseScoreTrendPoint, ...]
    drills: tuple[DemoDrillDefinition, ...]
    patch: DemoPatchDefinition | None = None


HACKATHON_MARKDOWN = """# DevOps x AI Agent Hackathon 2026 参加ガイド(デモ)

## テーマ
開発者は AI agent を活用し、設計から検証までの一連の改善を短いサイクルで示します。
単発の生成結果よりも、agent と人間の役割分担が明確な開発プロセスを重視します。

## 評価観点
審査では、課題設定の明確さ、agent 活用の深さ、実装の完成度、検証結果、
発表の分かりやすさを総合して見ます。

## 必須技術
提出物は GitHub 上で確認できること、主要な変更には自動テストまたは再現手順を
添えること、外部サービスを使う場合は必要な設定値を README にまとめることが求められます。

## 提出物
最終提出では GitHub repository、動作デモ、3 分以内の説明動画、
主要な設計判断のメモをそろえます。審査員が短時間で動作と意図を追える構成にしてください。
"""


EXPENSE_V1 = """# 経費精算の判断基準(デモ)

## 基本方針
業務に直接関係する支出は経費として申請できます。申請者は目的と金額を記録します。

## 確認項目
領収書があること、上長が内容を確認していること、同じ支出を重複申請していないことを確認します。
"""

EXPENSE_V2 = """# 経費精算の判断基準(デモ)

## 基本方針
業務に直接関係する支出は経費として申請できます。申請者は目的、金額、利用日を記録します。

## 確認項目
領収書または決済明細があること、上長が内容を確認していること、同じ支出を重複申請していないことを確認します。

## 金額別の扱い
1 万円未満は通常精算、1 万円以上は用途の説明を追加します。5 万円以上は事前承認の記録を添付します。
"""

EXPENSE_V3 = """# 経費精算の判断基準(デモ)

## 基本方針
業務に直接関係する支出は経費として申請できます。申請者は目的、金額、利用日を記録します。

## 確認項目
領収書または決済明細があること、上長が内容を確認していること、同じ支出を重複申請していないことを確認します。

## 金額別の扱い
1 万円未満は通常精算、1 万円以上は用途の説明を追加します。5 万円以上は事前承認の記録を添付します。

## 例外と期限
領収書を紛失した場合は支払証跡と紛失理由を添え、月末から 5 営業日以内に申請します。
接待費は参加者と目的を必ず記録します。
"""


def demo_course_definitions() -> tuple[DemoCourseDefinition, ...]:
    return (
        _hackathon_course(),
        _expense_course(),
    )


def _hackathon_course() -> DemoCourseDefinition:
    questions = (
        DrillQuestion(
            id="q1",
            question="このハッカソンで重視される開発プロセスを一文で説明してください。",
            intent="agent と人間の役割分担を理解しているか確認する。",
            rubric=[
                RubricItem(criterion="短い改善サイクルに触れている", points=2),
                RubricItem(criterion="agent と人間の役割分担に触れている", points=2),
            ],
            ideal_answer=(
                "AI agent と人間が役割分担し、設計から検証までを短い改善サイクルで"
                "示すことが重視されます。"
            ),
            source_evidence=[
                SourceEvidence(
                    section_heading="テーマ",
                    excerpt=(
                        "開発者は AI agent を活用し、設計から検証までの一連の改善を"
                        "短いサイクルで示します。"
                    ),
                ),
            ],
            max_score=4,
        ),
        DrillQuestion(
            id="q2",
            question="審査で見られる観点を 3 つ以上挙げてください。",
            intent="審査観点を本文から抽出できるか確認する。",
            rubric=[RubricItem(criterion="審査観点を 3 つ以上挙げている", points=4)],
            ideal_answer=(
                "課題設定、agent 活用、実装の完成度、検証結果、発表の分かりやすさなどが見られます。"
            ),
            source_evidence=[
                SourceEvidence(
                    section_heading="評価観点",
                    excerpt=(
                        "審査では、課題設定の明確さ、agent 活用の深さ、実装の完成度、検証結果、"
                    ),
                ),
            ],
            max_score=4,
        ),
        DrillQuestion(
            id="q3",
            question="最終提出で必要なものと、審査員が確認しやすくする工夫を説明してください。",
            intent="提出物と閲覧性を合わせて説明できるか確認する。",
            rubric=[
                RubricItem(criterion="提出物を具体的に挙げている", points=2),
                RubricItem(criterion="審査員が短時間で確認できる工夫に触れている", points=2),
            ],
            ideal_answer=(
                "GitHub repository、動作デモ、3 分以内の説明動画、設計判断メモをそろえ、"
                "審査員が短時間で動作と意図を追える構成にします。"
            ),
            source_evidence=[
                SourceEvidence(
                    section_heading="提出物",
                    excerpt="最終提出では GitHub repository、動作デモ、3 分以内の説明動画、",
                ),
            ],
            max_score=4,
        ),
    )
    return DemoCourseDefinition(
        slug="hackathon-guide",
        title="DevOps x AI Agent Hackathon 2026 参加ガイド(デモ)",
        drill_focus="審査員が提出物と評価観点を短時間で確認できるかを見る",
        markdown_versions=(HACKATHON_MARKDOWN,),
        score_trend=(CourseScoreTrendPoint(course_version=1, average_score=6.0, max_score=12),),
        drills=(
            DemoDrillDefinition(
                id_suffix="drill",
                share_token_suffix="share",
                course_version=1,
                status=DrillRunStatus.READY,
                questions=questions,
                answers=(
                    _hackathon_answer(
                        "a1",
                        "審査員A",
                        (
                            "AI agent が短い改善サイクルで開発します。",
                            "実装の完成度を見ます。",
                            "必要な提出物は分かりません。",
                        ),
                        (2, 0, 0),
                    ),
                    _hackathon_answer(
                        "a2",
                        "審査員B",
                        (
                            "AI agent と人間が役割分担し、設計から検証までを"
                            "短いサイクルで改善します。",
                            "課題設定の明確さと実装の完成度を見ます。",
                            "GitHub、動作デモ、3分以内の動画を用意します。",
                        ),
                        (4, 3, 3),
                    ),
                ),
            ),
        ),
    )


def _hackathon_answer(
    id_suffix: str,
    learner_name: str,
    answer_texts: tuple[str, str, str],
    scores: tuple[int, int, int],
) -> DemoAnswerDefinition:
    missing_for_submission = [
        "デモ URL が認証を要する場合の扱いが本文にないため、提出方法を判断できていない",
    ]
    results = (
        GradingResult(
            question_id="q1",
            score=scores[0],
            max_score=4,
            correct_points=["短い改善サイクルに触れている"] if scores[0] else [],
            missing_points=[] if scores[0] >= 4 else ["agent と人間の役割分担が弱い"],
            feedback=(
                "改善サイクルと役割分担を説明できています。"
                if scores[0] >= 4
                else "改善サイクルに加えて、agent と人間の役割分担も説明しましょう。"
            ),
            failure_tags=["process_gap"] if scores[0] < 4 else [],
        ),
        GradingResult(
            question_id="q2",
            score=scores[1],
            max_score=4,
            correct_points=["審査観点を具体的に挙げている"] if scores[1] else [],
            missing_points=[] if scores[1] >= 4 else ["審査観点が 3 つに届いていない"],
            feedback=(
                "評価観点を3つ以上説明できています。"
                if scores[1] >= 4
                else "課題設定、agent活用、検証結果など、評価観点を3つ以上挙げましょう。"
            ),
            failure_tags=["criteria_gap"] if scores[1] < 4 else [],
        ),
        GradingResult(
            question_id="q3",
            score=scores[2],
            max_score=4,
            correct_points=["複数の提出物に触れている"] if scores[2] else [],
            missing_points=missing_for_submission if scores[2] < 4 else [],
            feedback=(
                "提出物と確認しやすい構成を説明できています。"
                if scores[2] >= 4
                else "提出物に加えて、設計判断メモと審査員が迷わない公開条件も補足しましょう。"
            ),
            failure_tags=["submission_visibility_gap"] if scores[2] < 4 else [],
        ),
    )
    return DemoAnswerDefinition(
        id_suffix=id_suffix,
        learner_name=learner_name,
        answers_by_question=tuple(
            (question_id, answer_text)
            for question_id, answer_text in zip(("q1", "q2", "q3"), answer_texts, strict=True)
        ),
        total_score=sum(scores),
        grading_results=results,
    )


def _expense_course() -> DemoCourseDefinition:
    questions_v1 = _expense_questions(
        base_excerpt=(
            "業務に直接関係する支出は経費として申請できます。申請者は目的と金額を記録します。"
        ),
        confirmation_excerpt=(
            "領収書があること、上長が内容を確認していること、"
            "同じ支出を重複申請していないことを確認します。"
        ),
        base_ideal_answer="業務に直接関係する支出について、目的と金額を記録します。",
        confirmation_ideal_answer=("領収書、上長確認、重複申請がないことを確認します。"),
        policy_heading="確認項目",
        policy_excerpt="領収書があること、上長が内容を確認していること、",
        policy_question="領収書を紛失した場合の代替証跡と申請期限を説明してください。",
        policy_intent="教材だけで例外時の判断ができるか確認する。",
        policy_ideal_answer=(
            "教材には領収書紛失時の代替証跡と申請期限が記載されていないため、判断できません。"
        ),
        policy_criterion="教材の記載不足を具体的に指摘している",
    )
    questions_v2 = _expense_questions(
        base_excerpt=(
            "業務に直接関係する支出は経費として申請できます。"
            "申請者は目的、金額、利用日を記録します。"
        ),
        confirmation_excerpt=(
            "領収書または決済明細があること、上長が内容を確認していること、"
            "同じ支出を重複申請していないことを確認します。"
        ),
        base_ideal_answer=("業務に直接関係する支出について、目的、金額、利用日を記録します。"),
        confirmation_ideal_answer=(
            "領収書または決済明細、上長確認、重複申請がないことを確認します。"
        ),
        policy_heading="確認項目",
        policy_excerpt="領収書または決済明細があること、上長が内容を確認していること、",
        policy_question="領収書を紛失した場合の代替証跡と申請期限を説明してください。",
        policy_intent="教材だけで例外時の判断ができるか確認する。",
        policy_ideal_answer=(
            "教材には領収書紛失時の代替証跡と申請期限が記載されていないため、判断できません。"
        ),
        policy_criterion="教材の記載不足を具体的に指摘している",
    )
    questions_v3 = _expense_questions(
        base_excerpt=(
            "業務に直接関係する支出は経費として申請できます。"
            "申請者は目的、金額、利用日を記録します。"
        ),
        confirmation_excerpt=(
            "領収書または決済明細があること、上長が内容を確認していること、"
            "同じ支出を重複申請していないことを確認します。"
        ),
        base_ideal_answer=("業務に直接関係する支出について、目的、金額、利用日を記録します。"),
        confirmation_ideal_answer=(
            "領収書または決済明細、上長確認、重複申請がないことを確認します。"
        ),
        policy_heading="例外と期限",
        policy_excerpt=(
            "領収書を紛失した場合は支払証跡と紛失理由を添え、月末から 5 営業日以内に申請します。"
        ),
        policy_question="領収書を紛失した場合の証跡、理由、期限を説明してください。",
        policy_intent="例外時の代替証跡と期限を理解しているか確認する。",
        policy_ideal_answer=("支払証跡と紛失理由を添え、月末から5営業日以内に申請します。"),
        policy_criterion="代替証跡、紛失理由、申請期限を説明している",
    )
    return DemoCourseDefinition(
        slug="expense-policy",
        title="経費精算の判断基準(デモ・改善 3 周済み)",
        drill_focus="経費精算の承認判断で例外条件まで説明できるかを見る",
        markdown_versions=(EXPENSE_V1, EXPENSE_V2, EXPENSE_V3),
        score_trend=(
            CourseScoreTrendPoint(course_version=1, average_score=5.4, max_score=12),
            CourseScoreTrendPoint(course_version=2, average_score=8.7, max_score=12),
            CourseScoreTrendPoint(course_version=3, average_score=10.8, max_score=12),
        ),
        drills=(
            DemoDrillDefinition(
                id_suffix="drill-v1",
                share_token_suffix="share-v1",
                course_version=1,
                status=DrillRunStatus.ANALYZED,
                questions=questions_v1,
                answers=_expense_answers(
                    "v1",
                    ((1, 1, 1), (2, 2, 2), (2, 2, 2), (2, 2, 2), (2, 2, 2)),
                ),
            ),
            DemoDrillDefinition(
                id_suffix="drill-v2",
                share_token_suffix="share-v2",
                course_version=2,
                status=DrillRunStatus.ANALYZED,
                questions=questions_v2,
                answers=_expense_answers(
                    "v2",
                    (
                        (3, 3, 4),
                        (3, 3, 4),
                        (3, 3, 4),
                        (3, 3, 4),
                        (3, 2, 3),
                        (3, 2, 3),
                        (3, 2, 3),
                        (3, 2, 3),
                        (3, 2, 3),
                        (2, 2, 3),
                    ),
                ),
            ),
            DemoDrillDefinition(
                id_suffix="drill-v3",
                share_token_suffix="share-v3",
                course_version=3,
                status=DrillRunStatus.ANALYZED,
                questions=questions_v3,
                answers=_expense_answers(
                    "v3", ((4, 4, 4), (4, 4, 4), (4, 4, 4), (3, 3, 3), (3, 3, 3))
                ),
                analysis_timeline=_completed_timeline(),
            ),
        ),
        patch=DemoPatchDefinition(
            id_suffix="patch-v3",
            drill_id_suffix="drill-v3",
            base_markdown=EXPENSE_V2,
            patched_markdown=EXPENSE_V3,
            patch_summary="領収書紛失時の代替証跡、申請期限、接待費の記録条件を追記しました。",
            risk_notes=(
                "期限の営業日計算は社内カレンダーに合わせて確認してください。",
                "接待費の参加者記録は個人情報の扱いに注意してください。",
            ),
            failure_signals=(
                FailureSignal(
                    title="例外時の証跡不足",
                    severity=FailureSeverity.HIGH,
                    evidence=["領収書を紛失したケースの回答で判断が分かれた"],
                    likely_cause="v2 には領収書紛失時の代替証跡が書かれていない",
                    suspected_document_gap="例外時の支払証跡と紛失理由の扱いが不足",
                    target_sections=["例外と期限"],
                    recommended_change="領収書紛失時の代替証跡、申請期限、接待費の追加記録を追記する",
                    affected_count=6,
                    sample_size=10,
                    confidence_note="v2 の誤答が同じ例外条件に集中している",
                ),
            ),
            analysis_timeline=_completed_timeline(),
        ),
    )


def _expense_questions(
    *,
    base_excerpt: str,
    confirmation_excerpt: str,
    base_ideal_answer: str,
    confirmation_ideal_answer: str,
    policy_heading: str,
    policy_excerpt: str,
    policy_question: str,
    policy_intent: str,
    policy_ideal_answer: str,
    policy_criterion: str,
) -> tuple[DrillQuestion, ...]:
    return (
        _expense_question(
            question_id="q1",
            question="経費として申請できる支出と、申請者が記録すべき内容を説明してください。",
            intent="業務関連性と基本の申請情報を理解しているか確認する。",
            criterion="業務関連性と申請情報を説明している",
            ideal_answer=base_ideal_answer,
            section_heading="基本方針",
            excerpt=base_excerpt,
        ),
        _expense_question(
            question_id="q2",
            question="経費申請を承認する前に確認すべき証跡と重複防止項目を説明してください。",
            intent="証跡、上長確認、重複防止を理解しているか確認する。",
            criterion="証跡、上長確認、重複防止を説明している",
            ideal_answer=confirmation_ideal_answer,
            section_heading="確認項目",
            excerpt=confirmation_excerpt,
        ),
        _expense_question(
            question_id="q3",
            question=policy_question,
            intent=policy_intent,
            criterion=policy_criterion,
            ideal_answer=policy_ideal_answer,
            section_heading=policy_heading,
            excerpt=policy_excerpt,
        ),
    )


def _expense_question(
    *,
    question_id: str,
    question: str,
    intent: str,
    criterion: str,
    ideal_answer: str,
    section_heading: str,
    excerpt: str,
) -> DrillQuestion:
    return DrillQuestion(
        id=question_id,
        question=question,
        intent=intent,
        rubric=[RubricItem(criterion=criterion, points=4)],
        ideal_answer=ideal_answer,
        source_evidence=[SourceEvidence(section_heading=section_heading, excerpt=excerpt)],
        max_score=4,
    )


def _expense_answers(
    prefix: str,
    score_rows: tuple[tuple[int, int, int], ...],
) -> tuple[DemoAnswerDefinition, ...]:
    answers: list[DemoAnswerDefinition] = []
    for index, scores in enumerate(score_rows, start=1):
        answers.append(
            DemoAnswerDefinition(
                id_suffix=f"{prefix}-a{index}",
                learner_name=f"受講者{index}",
                answers_by_question=tuple(
                    (question_id, _expense_answer_text(prefix, question_id, score))
                    for question_id, score in zip(("q1", "q2", "q3"), scores, strict=True)
                ),
                total_score=sum(scores),
                grading_results=tuple(
                    _expense_grading_result(prefix, question_id, score)
                    for question_id, score in zip(("q1", "q2", "q3"), scores, strict=True)
                ),
            )
        )
    return tuple(answers)


def _expense_answer_text(prefix: str, question_id: str, score: int) -> str:
    if question_id == "q1":
        complete = (
            "業務に直接関係する支出について、目的と金額を記録します。"
            if prefix == "v1"
            else "業務に直接関係する支出について、目的、金額、利用日を記録します。"
        )
        partial = {
            1: "支出を経費として申請します。",
            2: "業務に関係する支出を申請します。",
            3: "業務に関係する支出について目的と金額を記録します。",
        }
        return complete if score >= 4 else partial[score]
    if question_id == "q2":
        complete = (
            "領収書、上長確認、重複申請がないことを確認します。"
            if prefix == "v1"
            else "領収書または決済明細、上長確認、重複申請がないことを確認します。"
        )
        partial = {
            1: "申請内容を確認します。",
            2: "領収書または決済明細を確認します。",
            3: "領収書または決済明細と上長確認を確認します。",
        }
        return complete if score >= 4 else partial[score]

    if prefix in {"v1", "v2"}:
        partial = {
            1: "領収書が必要です。",
            2: "領収書を紛失した場合は上長に確認します。",
            3: "教材には領収書を紛失した場合の扱いが書かれていません。",
        }
        return (
            "教材には領収書紛失時の代替証跡と申請期限が記載されていないため、判断できません。"
            if score >= 4
            else partial[score]
        )

    partial = {
        1: "領収書を紛失した場合も申請します。",
        2: "支払証跡を添えます。",
        3: "支払証跡と紛失理由を添えます。",
    }
    return (
        "支払証跡と紛失理由を添え、月末から5営業日以内に申請します。"
        if score >= 4
        else partial[score]
    )


def _expense_grading_result(prefix: str, question_id: str, score: int) -> GradingResult:
    if question_id == "q1":
        return GradingResult(
            question_id=question_id,
            score=score,
            max_score=4,
            correct_points=["業務関連性を確認している"] if score >= 2 else [],
            missing_points=[] if score >= 4 else ["申請者が記録する項目が不足"],
            feedback=(
                "対象支出と記録項目を説明できています。"
                if score >= 4
                else "業務関連性に加えて、目的、金額など教材記載の項目を挙げましょう。"
            ),
            failure_tags=["expense_basic_fields_gap"] if score < 4 else [],
        )
    if question_id == "q2":
        return GradingResult(
            question_id=question_id,
            score=score,
            max_score=4,
            correct_points=["証跡を確認している"] if score >= 2 else [],
            missing_points=[] if score >= 4 else ["上長確認または重複防止の説明が不足"],
            feedback=(
                "証跡、上長確認、重複防止を説明できています。"
                if score >= 4
                else "証跡だけでなく、上長確認と重複申請の確認も説明しましょう。"
            ),
            failure_tags=["expense_confirmation_gap"] if score < 4 else [],
        )
    if prefix in {"v1", "v2"}:
        return GradingResult(
            question_id=question_id,
            score=score,
            max_score=4,
            correct_points=["教材の記載不足を指摘している"] if score >= 3 else [],
            missing_points=(
                [] if score >= 4 else ["代替証跡と申請期限が教材にないことを特定できていない"]
            ),
            feedback=(
                "教材だけでは例外時の判断ができないことを具体的に指摘できています。"
                if score >= 4
                else "代替証跡と申請期限が教材に記載されていない点を具体化しましょう。"
            ),
            failure_tags=["expense_exception_gap"] if score < 4 else [],
        )
    return GradingResult(
        question_id=question_id,
        score=score,
        max_score=4,
        correct_points=["代替証跡に触れている"] if score >= 2 else [],
        missing_points=[] if score >= 4 else ["紛失理由または5営業日の期限が不足"],
        feedback=(
            "代替証跡、紛失理由、申請期限を説明できています。"
            if score >= 4
            else "支払証跡に加えて、紛失理由と5営業日の期限まで説明しましょう。"
        ),
        failure_tags=["expense_exception_deadline_gap"] if score < 4 else [],
    )


def _completed_timeline() -> tuple[AnalysisTimelineItem, ...]:
    return (
        AnalysisTimelineItem(
            id="collect_answers",
            title="回答データを収集",
            status=AnalysisStepStatus.COMPLETED,
            summary="採点済み回答を収集しました",
            evidence=["バージョン別の回答傾向を比較"],
            completed_at="2026-07-08T09:00:00+00:00",
        ),
        AnalysisTimelineItem(
            id="detect_failure_patterns",
            title="つまずき箇所を特定",
            status=AnalysisStepStatus.COMPLETED,
            summary="例外条件に関する誤答が集中していました",
            evidence=["領収書紛失時の判断が不安定"],
            completed_at="2026-07-08T09:01:00+00:00",
        ),
        AnalysisTimelineItem(
            id="match_course_evidence",
            title="教材の根拠を照合",
            status=AnalysisStepStatus.COMPLETED,
            summary="v2 には例外時の代替証跡がありませんでした",
            evidence=["例外と期限セクションが未定義"],
            completed_at="2026-07-08T09:02:00+00:00",
        ),
        AnalysisTimelineItem(
            id="decide_patch_strategy",
            title="改善方針を判断",
            status=AnalysisStepStatus.COMPLETED,
            summary="例外条件と期限を独立セクションとして追記します",
            evidence=["既存の金額別条件を壊さない追記"],
            completed_at="2026-07-08T09:03:00+00:00",
        ),
        AnalysisTimelineItem(
            id="create_patch",
            title="修正案を作成",
            status=AnalysisStepStatus.COMPLETED,
            summary="例外と期限セクションを追加しました",
            evidence=["diffText で追記箇所を確認可能"],
            completed_at="2026-07-08T09:04:00+00:00",
        ),
    )
