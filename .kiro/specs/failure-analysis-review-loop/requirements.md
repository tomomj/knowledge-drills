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

- **In scope**: 複数観点の所見収集、根拠評価と承認レビューの反復、承認結果に基づく早期終了または継続、承認済み所見だけを使う最終化、`FailureAnalysisOutput.reviewNotes` の optional 追加、Backend の timeline 変換、既存 UI での表示確認。
- **Out of scope**: ADK event streaming、SSE / WebSocket、専用 workflow viewer、新しい patch review agent、Chain-of-thought の保存・表示、既存 5 step timeline の大幅な再設計。
- **Adjacent expectations**: `hackathon-feedback-loop` の既存契約、`AnalysisTimeline` component、`AgentRuntimeClient` / `AdkAgentInvoker` の task mapping を維持する。受講者向け API には review note を出さない。

## Requirements

### Requirement 1: 根拠評価と承認レビューの反復

**Objective:** As a 講座オーナー, I want 誤答分析が並列分析後に根拠検証とレビューを受ける, so that 根拠の弱い改善提案が patch に流れにくくなる

#### Acceptance Criteria

1. When 回答分析が開始される, the 誤答分析機能 shall 根拠評価を開始する前に、定義された複数観点から所見を収集する
2. When 必要な所見の収集が完了する, the 誤答分析機能 shall 各所見を入力情報に照らして評価し、採用候補または棄却候補に分類して、その根拠、リスク、および最終化への指示を記録する
3. When 根拠評価が完了する, the 誤答分析機能 shall 評価とは別の承認レビューを行い、承認または修正要求の判定、問題点、修正指示、承認対象、および残存リスクを記録する
4. When 承認レビューが完了する, the 誤答分析機能 shall レビュー結果を保存した後に、その同じレビュー結果を使って反復の終了または継続を決定する
5. If 承認レビューが承認を返し、承認対象の参照が一意かつ採用候補に含まれる、または承認対象ゼロが明示される, the 誤答分析機能 shall 追加の根拠評価・承認レビューを実行せず、直ちに最終化へ進む
6. If 承認レビューが修正要求を返し、反復上限に達していない, the 誤答分析機能 shall 問題点と修正指示を次の根拠評価に反映して評価・レビュー cycle を継続する
7. When 修正要求を受けて次の根拠評価を行う, the 誤答分析機能 shall 前回指摘への対応内容と未解決事項を記録する
8. The 誤答分析機能 shall 評価・レビュー cycle に有限の反復上限を設ける
9. The 誤答分析機能 shall 各レビュー対象を収集済み所見とその出所・根拠へ追跡可能にし、同一 cycle の採用候補と棄却候補を重複させない
10. If レビュー判定、承認対象、または所見参照に重複、不明な参照、もしくは採用・棄却間の矛盾がある, the 誤答分析機能 shall その cycle を承認済みとして扱わない
11. When 承認レビューが承認される, the 誤答分析機能 shall そのレビューで明示的に承認された所見だけを Failure Signal の根拠として使用する
12. The 誤答分析機能 shall 承認状態を要約、理由、その他の自由文から推測しない
13. If 反復上限到達時に最新レビューが修正要求であるが有効な承認対象が存在する, the 誤答分析機能 shall その承認対象だけを部分採用し、未解決事項と残存リスクを最終結果に明示する
14. If 構造的に有効な最新レビューに承認対象が存在しない, the 誤答分析機能 shall 未承認所見を含めず、Failure Signal が空の最終結果と見送り理由を返して patch を提案しない
15. When 評価・レビュー cycle が終了する, the 誤答分析機能 shall 外部契約に適合する最終結果を一度だけ生成し、中間評価または中間レビューを最終結果として返さない

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
4. If timeline evidence が 3 件を超える場合, the backend shall evidence を最大 3 件に制御する
5. When frontend が timeline evidence を受け取る, the frontend shall 受け取った evidence をそのまま表示する
6. The implementation shall backend / frontend server を起動した手動 smoke で、分析開始から timeline 表示まで確認できる

### Requirement 5: 回帰検証と撤退経路

**Objective:** As a maintainer, I want review loop 追加後も既存 flow とテストが壊れない, so that hackathon 直前でも安全に切り戻せる

#### Acceptance Criteria

1. The Agent shall review loop を使わずに従来方式で誤答分析を実行できる撤退経路を維持する
2. The Agent tests shall 初回承認による早期終了、修正要求後の再評価、反復上限時の部分採用、承認対象ゼロ時の見送り、不正な所見参照の拒否、および最終結果が一度だけ生成されることを検証する
3. The Backend tests shall `reviewNotes` あり・なし、既存 evidence との併存、最大 3 件制限、`timelineStep` による振り分けを検証する
4. The Frontend tests shall review 結果を含む timeline item が表示されることを検証する
5. The implementation shall 実行可能な範囲で agent / backend / frontend のテストを通し、実行できない検証は理由を記録する
6. When review loop を有効にする, the implementation shall local と production の設定済み timeout budget で分析が完了するかを smoke で確認し、不足する場合は必要な設定変更を記録する
