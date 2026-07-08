# Requirements Document

## Introduction

Hackathon Feedback Loop は、Knowledge Drills の中核体験である
「教材 Markdown -> 根拠付きドリル生成 -> 回答収集 -> 誤答分析 -> Markdown patch -> 改善効果の確認」
という改善ループを、審査員・講座オーナーに証拠付きで見せられる状態にする機能群である。

目的は問題編集機能を増やすことではなく、
「受講者のつまずきをテレメトリとして、教材が改善ループに入った」ことを
画面上の観測値・根拠・判断ログ・Before / After 数値で示すことである。

実装仕様の正は本 spec（`.kiro/specs/hackathon-feedback-loop/` の requirements / design / tasks）とする。
`docs/hackathon-feedback-loop-feature-design.md` は UI 文言・プロンプト方針などの背景資料であり、矛盾する場合は本 spec を優先する。

## Boundary Context

- **In scope**: 出題観点（drillFocus）の入力・保存・ドリル生成への伝搬、設問根拠（sourceEvidence.excerpt）の教材実在検証、分析前の採点状況集計（scoreSummary）、分析実行タイムラインと判断ログの保存・表示、誤答分析の多視点化（従来方式への設定切り替え付き）、講座 version 間の Before / After 改善メトリクス。
- **Out of scope**: 質問文の直接入力、生成済み設問の個別編集・1 問だけ再生成、問題
バンク、LMS 連携、SSE / WebSocket / background worker の導入、patch レビュー専用エージェントの追加、Chain-of-thought（内部推論文・プロンプト本文）の表示、通知機能。
- **Adjacent expectations**: 認証・所有権判定は google-login-owner-scope に依存し、本機能は owner 判定済みの管理 API / 画面にのみ管理情報を追加する。受講者向け share URL はログイン不要のまま維持する。エージェント出力品質の回帰検知は既存の agent eval CI が担う。

## Requirements

### Requirement 1: 出題観点（drillFocus）の管理

**Objective:** As a 講座オーナー, I want 出題してほしい観点を講座に登録できる, so that ドリルが業務上重要な観点を優先して出題する

#### Acceptance Criteria

1. When オーナーが講座を作成または更新する, the Knowledge Drills backend shall 任意入力の出題観点（drillFocus）を講座に保存する
2. When 出題観点が trim 後に空文字である, the Knowledge Drills backend shall 出題観点を未設定（null）として扱う
3. If 出題観点が 500 文字を超える, the Knowledge Drills backend shall validation error を返し、the Knowledge Drills frontend shall 「出題したい観点は 500 文字以内で入力してください。」を表示する
4. When 講座の title・markdown・出題観点のいずれかが更新される, the Knowledge Drills backend shall 講座 version を 1 増やし、revision に出題観点を保存する
5. When オーナーがドリルを生成する, the Knowledge Drills backend shall 生成時点の出題観点を drill run に snapshot として保存し、ドリル生成入力に含める
6. When オーナーが Drill Admin を開く, the Knowledge Drills frontend shall 生成時の出題観点を表示する
7. When 出題観点が未設定である, the Knowledge Drills backend shall 既存どおりドリルを生成する
8. The Knowledge Drills shall 受講者向け画面・受講者向け API レスポンスに出題観点を含めない

### Requirement 2: 根拠付きドリル生成の保証

**Objective:** As a 講座オーナー, I want すべての設問が教材 Markdown に実在する根拠を持つ, so that 無根拠な設問が受講者に配布されない

#### Acceptance Criteria

1. When ドリル生成結果を受け取る, the Knowledge Drills backend shall 各設問の sourceEvidence が空でないこと、および各 excerpt が教材 Markdown に含まれることを検証する
2. If sourceEvidence の excerpt が教材 Markdown に存在しない、または trim 後に空である, the Knowledge Drills backend shall drill run を failed にし、設問を受講者に配布しない
3. When 出題観点が指定されている, the ドリル生成機能 shall 出題観点を設問の観点として優先しつつ、教材 Markdown に根拠がある内容のみを出題する
4. If 出題観点に対応する記述が教材 Markdown に存在しない, the ドリル生成機能 shall 教材 Markdown に実在する内容のみで出題し、出題観点由来の業務ルール・数値・例外条件を補わない
5. While local 実行モードで動作している, the ドリル生成機能 shall 教材 Markdown の本文から sourceEvidence を作成し、教材と無関係な固定 excerpt を返さない

### Requirement 3: 分析前の採点状況の可視化

**Objective:** As a 講座オーナー, I want 分析を実行する前に採点状況が見える, so that 分析を実行すべきか判断できる

#### Acceptance Criteria

1. When オーナーが Drill Admin を開く, the Knowledge Drills frontend shall 採点済み回答数・平均点・満点を表示する
2. When 採点済み回答が 1 件以上ある, the Knowledge Drills frontend shall 設問ごとの平均点と、よく欠落する観点（commonMissingPoints・failureTags）を表示する
3. If 採点済み回答が 0 件である, the Knowledge Drills frontend shall 「採点済み回答がまだありません」を表示し、分析開始操作を無効化する
4. When 採点済み回答が 0 件である, the Knowledge Drills backend shall 平均点を未計測（null）として返す
5. The Knowledge Drills shall 受講者向け画面に採点集計・rubric・模範解答を表示しない
6. The Knowledge Drills backend shall 分析開始可否（canAnalyze）を回答総数ではなく採点済み回答数に基づいて返す
7. The Knowledge Drills backend shall 採点集計の対象を採点完了（graded）の回答のみとし、採点中・採点失敗の回答を含めない

### Requirement 4: 分析実行の可視化（タイムラインと判断ログ）

**Objective:** As a 講座オーナー, I want 分析 Agent が何を観測しどう判断したかが見える, so that patch 提案の根拠を確認して適用を判断できる

#### Acceptance Criteria

1. When オーナーが回答分析を開始する, the Knowledge Drills backend shall 分析の各段階（回答データを収集、つまずき箇所を特定、教材の根拠を照合、改善方針を判断、修正案を作成）の状態と 1 行要約・根拠を段階的に保存する
2. While 分析が実行中である, the Knowledge Drills frontend shall 分析 Agent の実行状況を数秒以内の間隔で更新表示する
3. When 分析が完了して patch が作成される, the Knowledge Drills backend shall 完了時点のタイムラインを patch に保存する
4. When オーナーが Patch Review を開く, the Knowledge Drills frontend shall 分析 Agent の判断ログ（タイムライン）を patch summary と failure signal の間に表示する
5. If 分析が失敗する, the Knowledge Drills backend shall 実行中の段階を failed にし、失敗を error message として記録したうえで、drill run を配布可能な状態に戻す
6. The Knowledge Drills shall タイムラインに観測値・根拠・判断結果のみを表示し、内部推論文・プロンプト本文を保存または表示しない
7. The Knowledge Drills shall 受講者向け画面・受講者向け API レスポンスにタイムラインを含めない
8. While 分析が実行中・分析完了後・分析失敗後のいずれかである, the Knowledge Drills backend shall share URL による受講者のドリル取得・回答を引き続き許可する（生成失敗の drill run のみ配布不可とする）

### Requirement 5: 誤答分析の多視点化

**Objective:** As a 講座オーナー, I want 誤答分析が複数の固定観点から検討される, so that 教材ギャップ・設問品質・つまずきパターンの見落としが減る

#### Acceptance Criteria

1. When 回答分析が実行される, the 誤答分析機能 shall 教材ギャップ・設問品質・つまずきパターンの 3 観点で誤答を検討し、結果を 1 つの分析結果に統合する
2. The 誤答分析機能 shall 従来の分析結果と互換の形式で結果を返し、既存の patch 提案フローを変更なく通過させる
3. Where 多視点分析が有効である, the Knowledge Drills shall 各観点の 1 行要約をタイムラインの根拠として表示する
4. When 運用者が設定で従来方式（単一分析）を指定する, the 誤答分析機能 shall 多視点分析を行わず従来の単一分析で実行する
5. If 多視点分析の実行が失敗する, the Knowledge Drills backend shall Requirement 4 の分析失敗と同様に扱う

### Requirement 6: 改善効果の可視化（Before / After）

**Objective:** As a 講座オーナー, I want patch 適用前後の成績を比較できる, so that 教材改善の効果をデータで確認できる

#### Acceptance Criteria

1. When オーナーが講座の改善メトリクスを要求する, the Knowledge Drills backend shall drill run ごとに講座 version・回答数・平均点・満点を返す
2. When 講座に採点済み回答を持つ drill run が複数ある, the Knowledge Drills frontend shall 講座画面で version 間の平均点比較を表示する
3. If 採点済み回答が存在しない drill run がある, the Knowledge Drills backend shall その drill run の平均点を未計測（null）として返す
4. When 他の利用者の講座の改善メトリクスが要求される, the Knowledge Drills backend shall owner check により拒否する
5. The Knowledge Drills shall 受講者向け画面に改善メトリクスを表示しない
