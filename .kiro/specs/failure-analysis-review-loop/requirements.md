# Requirements Document

## Introduction

Failure Analysis Review Loop は、既存の Hackathon Feedback Loop に対して、
誤答分析 Agent の深さを追加し、その判断を講座オーナーと審査員に見える形で提示するための追加仕様である。

既存の `hackathon-feedback-loop` spec は、3 観点の多視点分析と分析タイムライン表示までを扱っている。
本 spec はその上に、`evidence_critic` と `critic_reviewer` による検証ループ、
および review 結果を既存 UI の `AnalysisTimeline` に表示する契約を追加する。

目的は「patch が出た」ことではなく、
「Agent が並列に文脈を集め、根拠の弱い所見を落とし、レビューで承認された判断だけが改善案に流れた」
ことを、画面上の要約と根拠で説明できる状態にすることである。

## Boundary Context

- **In scope**: failure analysis agent の `analyst_parallel -> review_loop -> finalizer` 化、critic / reviewer 用 schema・prompt、`FailureAnalysisOutput.reviewNotes` の optional 追加、Backend の timeline 変換、既存 UI での表示確認。
- **Out of scope**: ADK event streaming、SSE / WebSocket、専用 workflow viewer、新しい patch review agent、Chain-of-thought の保存・表示、既存 5 step timeline の大幅な再設計。
- **Adjacent expectations**: `hackathon-feedback-loop` の既存契約、`AnalysisTimeline` component、`AgentRuntimeClient` / `AdkAgentInvoker` の task mapping を維持する。受講者向け API には review note を出さない。

## Requirements

### Requirement 1: Agent workflow の検証ループ化

**Objective:** As a 講座オーナー, I want 誤答分析が並列分析後に根拠検証とレビューを受ける, so that 根拠の弱い改善提案が patch に流れにくくなる

#### Acceptance Criteria

1. When 回答分析が実行される, the 誤答分析機能 shall `analyst_parallel` で複数観点の所見を並列に集める
2. When 並列分析が完了する, the 誤答分析機能 shall `evidence_critic` が `EvidenceReviewOutput` として採用所見・棄却所見・finalizer への指示・リスク・修正履歴を state に保存する
3. When `evidence_critic` が評価を返す, the 誤答分析機能 shall `critic_reviewer` が `CriticReviewOutput` として `verdict`、`issues`、`revisionInstructions`、`approvedFindingIds`、`riskNotes` を state に保存する
4. If `critic_reviewer` が `approved` を返す, the 誤答分析機能 shall `exit_loop` により review loop を終了する
5. If `critic_reviewer` が `needs_revision` を返す, the 誤答分析機能 shall 次 iteration の `evidence_critic` が reviewer 指摘を読んで評価を修正できる
6. The 誤答分析機能 shall review loop に最大 iteration 数を設定し、無限ループを防ぐ
7. The 誤答分析機能 shall 最後の `finalizer` だけが backend に返す `FailureAnalysisOutput` を生成する
8. The `finalizer` shall `criticReview.approvedFindingIds` に含まれる finding だけを Failure Signal の根拠として採用し、自由文から承認済み扱いを推測しない
9. If review loop が最大 iteration に到達しても `verdict=approved` にならない, the `finalizer` shall 最新の `approvedFindingIds` が非空ならその finding だけを採用し、`approvedFindingIds` が空なら有効な `FailureAnalysisOutput` を生成せず分析失敗として扱わせる

### Requirement 2: 安定した FailureAnalysis 契約

**Objective:** As a backend implementer, I want Agent の中間判断を安定 JSON として受け取れる, so that UI が ADK workflow 内部や event stream に依存せず表示できる

#### Acceptance Criteria

1. The `FailureAnalysisOutput` shall 既存の `failureSignals` と optional `perspectives` を維持する
2. The `FailureAnalysisOutput` shall optional `reviewNotes` を追加し、critic / reviewer / finalizer の表示用要約を返せる
3. The `reviewNotes` shall `id`、`source`、`timelineStep`、`title`、`summary`、`evidence` を持つ
4. When `reviewNotes` が存在しない旧応答または single mode 応答を backend が受け取る, the backend shall 従来どおり分析と patch 作成を完了できる
5. The `reviewNotes` shall 内部推論文、プロンプト本文、Chain-of-thought を含めない
6. The Agent schema and Backend schema shall camelCase serialization を維持する
7. The backend shall `reviewNotes.id` の文字列内容に依存して timeline step を判定せず、`timelineStep` field のみを振り分け根拠にする

### Requirement 3: Backend timeline への review 結果反映

**Objective:** As a 講座オーナー, I want Agent のレビュー判断が既存タイムラインに表示される, so that patch 提案の信頼性を判断できる

#### Acceptance Criteria

1. When `perspectives` が返る, the backend shall `detect_failure_patterns` step の evidence として観点別所見を表示する
2. When `reviewNotes.timelineStep` が `match_course_evidence` である, the backend shall その review note を教材根拠照合 step の evidence として反映する
3. When `reviewNotes.timelineStep` が `decide_patch_strategy` である, the backend shall その review note を改善方針判断 step の evidence として反映する
4. If `reviewNotes` が空である, the backend shall 既存の timeline 表示を維持する
5. The backend shall review note を `DrillRun.analysisTimeline` と `DocumentPatch.analysisTimeline` に保存する
6. The backend shall 受講者向け API に `reviewNotes` または timeline を含めない
7. When review note 由来 evidence と既存 evidence が同じ step に存在する, the backend shall review note 由来 evidence を先頭に置き、その後に既存 evidence を重複排除して追加し、各 step の evidence を最大 3 件に制限する
8. When review note 由来 evidence が存在しない, the backend shall 既存 evidence の順序と内容を維持する

### Requirement 4: 既存 UI での表示と挙動確認

**Objective:** As a 審査員, I want 新しい Agent workflow の判断が既存画面で確認できる, so that demo 中に Agent の深さを説明できる

#### Acceptance Criteria

1. When オーナーが Drill Admin で分析を開始する, the frontend shall 既存 polling により review 結果を含む timeline を表示する
2. When オーナーが Patch Review を開く, the frontend shall patch summary と failure signals の間に review 結果を含む timeline を表示する
3. The frontend shall 専用 workflow viewer を追加せず、既存 `AnalysisTimeline` component を使う
4. If timeline evidence が 3 件を超える場合, the backend shall evidence を最大 3 件に制御し、the frontend shall 受け取った evidence をそのまま表示する
5. The implementation shall backend / frontend server を起動した手動 smoke で、分析開始から timeline 表示まで確認できる

### Requirement 5: 回帰検証と撤退経路

**Objective:** As a maintainer, I want review loop 追加後も既存 flow とテストが壊れない, so that hackathon 直前でも安全に切り戻せる

#### Acceptance Criteria

1. The Agent shall `KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE=single` による従来方式の撤退経路を維持する
2. The Agent tests shall workflow 構造、finalizer の `output_schema`、中間 agent の `output_key`、`EvidenceReviewOutput`、`CriticReviewOutput.verdict`、`approvedFindingIds` を検証する
3. The Backend tests shall `reviewNotes` あり・なし、既存 evidence との併存、最大 3 件制限、`timelineStep` による振り分けを検証する
4. The Frontend tests shall review 結果を含む timeline item が表示されることを検証する
5. The implementation shall 実行可能な範囲で agent / backend / frontend のテストを通し、実行できない検証は理由を記録する
6. The implementation shall review loop の LLM 呼び出し増加を踏まえ、local default 60 秒と production Terraform 120 秒の timeout で足りるかを smoke で確認し、不足する場合は `KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS` または Terraform の timeout 設定変更を明示する
