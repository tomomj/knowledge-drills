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
    answer_text: str
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
            rubric=[RubricItem(criterion="短い改善サイクルに触れている", points=1)],
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
            max_score=1,
        ),
        DrillQuestion(
            id="q2",
            question="審査で見られる観点を 3 つ以上挙げてください。",
            intent="審査観点を本文から抽出できるか確認する。",
            rubric=[RubricItem(criterion="審査観点を 3 つ以上挙げている", points=1)],
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
            max_score=1,
        ),
        DrillQuestion(
            id="q3",
            question="最終提出で必要なものと、審査員が確認しやすくする工夫を説明してください。",
            intent="提出物と閲覧性を合わせて説明できるか確認する。",
            rubric=[
                RubricItem(criterion="提出物を具体的に挙げている", points=1),
                RubricItem(criterion="審査員が短時間で確認できる工夫に触れている", points=1),
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
            max_score=2,
        ),
    )
    return DemoCourseDefinition(
        slug="hackathon-guide",
        title="DevOps x AI Agent Hackathon 2026 参加ガイド(デモ)",
        drill_focus="審査員が提出物と評価観点を短時間で確認できるかを見る",
        markdown_versions=(HACKATHON_MARKDOWN,),
        score_trend=(CourseScoreTrendPoint(course_version=1, average_score=2.0, max_score=4),),
        drills=(
            DemoDrillDefinition(
                id_suffix="drill",
                share_token_suffix="share",
                course_version=1,
                status=DrillRunStatus.READY,
                questions=questions,
                answers=(
                    _hackathon_answer("a1", "審査員A", "agent で作ったものを提出する。", (0, 1, 0)),
                    _hackathon_answer(
                        "a2", "審査員B", "短い改善サイクルと GitHub、動画を用意する。", (1, 1, 1)
                    ),
                ),
            ),
        ),
    )


def _hackathon_answer(
    id_suffix: str,
    learner_name: str,
    answer_text: str,
    scores: tuple[int, int, int],
) -> DemoAnswerDefinition:
    missing_for_submission = [
        "デモ URL が認証を要する場合の扱いが本文にないため、提出方法を判断できていない",
    ]
    results = (
        GradingResult(
            question_id="q1",
            score=scores[0],
            max_score=1,
            correct_points=["改善サイクルに触れている"] if scores[0] else [],
            missing_points=[] if scores[0] else ["agent と人間の役割分担が弱い"],
            feedback="改善サイクルと役割分担を本文に沿って説明しましょう。",
            failure_tags=["process_gap"] if not scores[0] else [],
        ),
        GradingResult(
            question_id="q2",
            score=scores[1],
            max_score=1,
            correct_points=["審査観点を複数挙げている"] if scores[1] else [],
            missing_points=[] if scores[1] else ["審査観点が 3 つに届いていない"],
            feedback="評価観点の列挙を 3 つ以上に増やしましょう。",
            failure_tags=["criteria_gap"] if not scores[1] else [],
        ),
        GradingResult(
            question_id="q3",
            score=scores[2],
            max_score=2,
            correct_points=["提出物に触れている"] if scores[2] else [],
            missing_points=missing_for_submission if scores[2] < 2 else [],
            feedback="提出物に加えて、審査員が迷わない公開条件も補足できるとよいです。",
            failure_tags=["submission_visibility_gap"] if scores[2] < 2 else [],
        ),
    )
    return DemoAnswerDefinition(
        id_suffix=id_suffix,
        learner_name=learner_name,
        answer_text=answer_text,
        total_score=sum(scores),
        grading_results=results,
    )


def _expense_course() -> DemoCourseDefinition:
    question_v1 = _expense_question(
        section_heading="基本方針",
        excerpt="業務に直接関係する支出は経費として申請できます。",
    )
    question_v2 = _expense_question(
        section_heading="金額別の扱い",
        excerpt="1 万円未満は通常精算、1 万円以上は用途の説明を追加します。",
    )
    question_v3 = _expense_question(
        section_heading="例外と期限",
        excerpt=(
            "領収書を紛失した場合は支払証跡と紛失理由を添え、月末から 5 営業日以内に申請します。"
        ),
    )
    return DemoCourseDefinition(
        slug="expense-policy",
        title="経費精算の判断基準(デモ・改善 3 周済み)",
        drill_focus="経費精算の承認判断で例外条件まで説明できるかを見る",
        markdown_versions=(EXPENSE_V1, EXPENSE_V2, EXPENSE_V3),
        score_trend=(
            CourseScoreTrendPoint(course_version=1, average_score=1.8, max_score=4),
            CourseScoreTrendPoint(course_version=2, average_score=2.9, max_score=4),
            CourseScoreTrendPoint(course_version=3, average_score=3.6, max_score=4),
        ),
        drills=(
            DemoDrillDefinition(
                id_suffix="drill-v1",
                share_token_suffix="share-v1",
                course_version=1,
                status=DrillRunStatus.ANALYZED,
                questions=(question_v1,),
                answers=_expense_answers("v1", (1, 2, 2, 2, 2)),
            ),
            DemoDrillDefinition(
                id_suffix="drill-v2",
                share_token_suffix="share-v2",
                course_version=2,
                status=DrillRunStatus.ANALYZED,
                questions=(question_v2,),
                answers=_expense_answers("v2", (3, 3, 3, 3, 3, 3, 3, 3, 3, 2)),
            ),
            DemoDrillDefinition(
                id_suffix="drill-v3",
                share_token_suffix="share-v3",
                course_version=3,
                status=DrillRunStatus.ANALYZED,
                questions=(question_v3,),
                answers=_expense_answers("v3", (4, 4, 4, 3, 3)),
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


def _expense_question(section_heading: str, excerpt: str) -> DrillQuestion:
    return DrillQuestion(
        id="q1",
        question="経費精算を承認できるか、必要な確認項目と例外条件を説明してください。",
        intent="金額、証跡、例外、期限を踏まえて判断できるか確認する。",
        rubric=[
            RubricItem(criterion="業務関連性と証跡を確認している", points=1),
            RubricItem(criterion="金額別の追加条件を説明している", points=1),
            RubricItem(criterion="例外時の証跡と理由に触れている", points=1),
            RubricItem(criterion="申請期限または接待費の追加記録に触れている", points=1),
        ],
        ideal_answer=(
            "業務関連性、領収書または決済明細、金額別条件を確認し、"
            "紛失時は支払証跡と理由、期限や接待費の参加者記録も確認します。"
        ),
        source_evidence=[
            SourceEvidence(
                section_heading=section_heading,
                excerpt=excerpt,
            ),
        ],
        max_score=4,
    )


def _expense_answers(prefix: str, scores: tuple[int, ...]) -> tuple[DemoAnswerDefinition, ...]:
    answers: list[DemoAnswerDefinition] = []
    for index, score in enumerate(scores, start=1):
        answers.append(
            DemoAnswerDefinition(
                id_suffix=f"{prefix}-a{index}",
                learner_name=f"受講者{index}",
                answer_text="業務関連性、証跡、金額条件、例外条件を確認します。",
                total_score=score,
                grading_results=(
                    GradingResult(
                        question_id="q1",
                        score=score,
                        max_score=4,
                        correct_points=["業務関連性と証跡を確認できている"],
                        missing_points=[] if score >= 4 else ["例外条件または期限の説明が不足"],
                        feedback="例外条件と期限まで含めると判断が安定します。",
                        failure_tags=["expense_exception_gap"] if score < 4 else [],
                    ),
                ),
            )
        )
    return tuple(answers)


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
