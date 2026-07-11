# Requirements Document

## Introduction

Knowledge Drills の講座オーナーは、誤答テレメトリ（回答）が貯まっていても「気が向いたときに分析ボタンを押す」
手動検知しかできない。DevOps の絵で言うと monitoring はあるが alerting がない状態で、どの資料が悲鳴を
上げているかは講座一覧を開いただけでは分からない（GitHub issue #75）。

本 spec は、未分析の低スコア回答が閾値を超えた講座を「要分析」状態と判定し、講座一覧の講座カードと
ドリル管理画面の分析実行導線付近にアラートバッジとして表示する。これにより
monitoring → alerting → human triage（分析実行）→ human gate（patch apply）の改善ループが画面上で成立し、
docs/blog.md の「ドキュメントに DevOps を」の主張を裏付ける。

運用上の制約として、デモ動画撮影（1カット目: 2講座並んで片方が警告）より前のマージが必要である
（ハッカソン締切 2026-07-12 23:59。優先度は P0 タスク群より後の任意タスク）。

## Boundary Context

- **In scope**: 要分析状態の判定ルールとその判定基盤（分析済み回答件数の記録・初期化）、講座一覧および
  ドリル管理画面のレスポンスへの判定結果の追加、講座一覧カードとドリル管理画面でのバッジ表示、
  デモシードデータとの整合検証、docs/blog.md の更新。
- **Out of scope**: 通知チャネル（メール / Slack 等）、分析の自動実行（起動の自動化）、分析エージェント側
  （分析内容・プロンプト）の変更、needsAnalysis および集計値の事前計算・永続化、SSE / WebSocket /
  Firestore Listener によるリアルタイム更新、ドリル管理画面の常時ポーリング（既存の分析実行中 1 秒
  ポーリングは維持）、講座詳細画面へのバッジ追加、シードデータの変更、既存分析済みドリルへの一括バックフィル。
- **Adjacent expectations**: 分析実行の可否表現（`analysis-ui-declutter` が定めた「実行可否はボタンの
  活性状態でのみ表現し、独立チップを出さない」ルール）を壊さない。講座一覧の既存「分析できます」チップと
  デモシードデータは `demo-course-seed` の所有物であり、本 spec はチップの表示条件にのみ介入し、
  シードデータには介入しない。分析パイプラインの判断内容は `failure-analysis-review-loop` の所有であり、
  本 spec が分析処理に求めるのは完了時の分析済み件数の記録のみである。

## Requirements

### Requirement 1: 要分析状態の判定

**Objective:** As a 講座オーナー, I want 分析が必要な講座が自動判定される, so that 回答状況を手動で調べなくても悲鳴を上げている資料に気付ける

#### Acceptance Criteria

1. When 講座の要分析状態が判定される, the Knowledge Drills backend shall 「現行の資料 version への未分析回答が閾値件数以上」かつ「現行の資料 version の平均スコア率が閾値未満」の両方を満たす場合に限り要分析と判定する
2. The Knowledge Drills backend shall 要分析判定の初期閾値として「未分析回答 1 件以上」「平均スコア率 70% 未満」を用いる
3. When 未分析回答件数および平均スコア率を集計する, the Knowledge Drills backend shall 採点が完了した回答のみを集計対象とし、採点中・採点失敗・スコア未確定の回答を除外する
4. When 平均スコア率を算出する, the Knowledge Drills backend shall 現行の資料 version に紐づく採点済み回答全体（分析済みを含む）の得点率の平均を用いる
5. If 現行の資料 version の採点済み回答が 0 件である、または平均スコア率が算出できない, the Knowledge Drills backend shall 要分析と判定しない
6. While ドリルの分析が実行中である, the Knowledge Drills backend shall そのドリルの回答を未分析回答件数に算入しない
7. While ドリルが生成中または生成失敗の状態である, the Knowledge Drills backend shall そのドリルの回答を未分析回答件数に算入しない
8. When 分析未実施のドリルの未分析回答件数を数える, the Knowledge Drills backend shall そのドリルの採点済み回答の全件を未分析として数える
9. When 分析済みのドリルの未分析回答件数を数える, the Knowledge Drills backend shall 採点済み回答件数から記録済みの分析済み回答件数を差し引いた件数（0 未満にしない）を未分析として数える
10. If 分析済みのドリルに分析済み回答件数が未記録である, the Knowledge Drills backend shall そのドリルの未分析回答件数を 0 件として扱う
11. When 講座一覧またはドリル管理情報が取得される, the Knowledge Drills backend shall その時点の回答・分析状態を反映した要分析判定を返す

### Requirement 2: 分析済み回答件数の記録

**Objective:** As a 講座オーナー, I want 分析済みの回答と未分析の回答が正しく区別される, so that 分析完了後に届いた新しい誤答も見逃されない

#### Acceptance Criteria

1. When ドリルの分析が成功する, the Knowledge Drills backend shall 分析開始時に収集して実際に分析へ渡した採点済み回答の件数を、そのドリルの分析済み回答件数として記録する
2. If ドリルの分析が失敗する, the Knowledge Drills backend shall 分析済み回答件数を更新せず、対象の回答を未分析のまま維持する
3. If 分析の実行中に新しい回答が届く, the Knowledge Drills backend shall その回答を分析済みとして扱わず、分析完了後も未分析回答として数える
4. When 分析済み回答件数が未記録の分析済みドリルに新しい回答が受け付けられる, the Knowledge Drills backend shall その回答を保存する前に、保存前時点の採点済み回答件数を分析済み回答件数として一度だけ初期化する
5. While 分析完了時の記録と回答受付時の初期化が並行して行われる, the Knowledge Drills backend shall 分析完了時に記録された分析済み回答件数を初期化によって失わない
6. The Knowledge Drills backend shall 分析済み回答件数を単調非減少とし、いかなる更新でも記録済みの値より小さい値へ後退させない
7. If 分析済み回答件数の初期化に失敗する, the Knowledge Drills backend shall 新しい回答を保存せずエラーを返し、初期化されないまま回答だけが増える状態を作らない
8. When 回答受付時に分析済み回答件数を初期化する, the Knowledge Drills backend shall ドリルの分析状況・分析タイムラインを変更しない
9. When 分析成功時に分析済み回答件数を記録する, the Knowledge Drills backend shall 既存の分析完了に伴う状態遷移・タイムライン更新を維持し、それ以外のドリルの状態を上書きしない

### Requirement 3: 両画面への判定結果の提供

**Objective:** As a 講座オーナー, I want 講座一覧とドリル管理画面が同じ要分析判定を示す, so that 画面によって矛盾したアラートを見ることがない

#### Acceptance Criteria

1. When 講座一覧が取得される, the Knowledge Drills backend shall 各講座に要分析判定を含めて返す
2. When 現行の資料 version のドリルの管理情報が取得される, the Knowledge Drills backend shall 講座一覧と同一の判定ルールで算出した要分析判定を含めて返し、同じ回答・分析状態に対して講座一覧と同じ判定を返す
3. If 現行より古い資料 version のドリルの管理情報が取得される, the Knowledge Drills backend shall そのドリルを要分析として扱わない

### Requirement 4: 講座一覧のアラートバッジと定期更新

**Objective:** As a 講座オーナー, I want 講座一覧が監視画面として最新のアラート状態を示し続ける, so that 画面を開いたままでも悲鳴を上げている講座に気付ける

#### Acceptance Criteria

1. When 要分析と判定された講座が講座一覧に表示される, the Knowledge Drills frontend shall その講座カードに警告トーンのアラートバッジ（表示文言例: 「低スコア回答が蓄積 — 分析推奨」）を表示する
2. While 講座のアラートバッジが点灯している, the Knowledge Drills frontend shall 同じ講座カードに既存の「分析できます」チップを表示せず、アラートバッジで置き換える
3. While 講座が要分析と判定されていない, the Knowledge Drills frontend shall 既存の講座カード表示（「分析できます」チップを含む）を変更しない
4. While 講座一覧が表示されている, the Knowledge Drills frontend shall 15 秒間隔で講座一覧 API を再取得し、最新の要分析判定を表示する
5. While 再取得が実行中である, the Knowledge Drills frontend shall 現在の講座一覧を表示し続ける
6. If 再取得に失敗する, the Knowledge Drills frontend shall 最後に成功した一覧を維持する
7. While 前回の取得が完了していない, the Knowledge Drills frontend shall 次の取得を開始しない
8. When 講座一覧のページを離れる, the Knowledge Drills frontend shall ポーリングを停止する

### Requirement 5: ドリル管理画面のアラート表示

**Objective:** As a 講座オーナー, I want 分析を実行する画面でも要分析アラートが見える, so that アラートに気付いてから分析実行までが同じ画面で完結する

#### Acceptance Criteria

1. When 要分析と判定された講座の現行の資料 version のドリル管理画面が表示される, the Knowledge Drills frontend shall 分析実行導線（「回答を分析する」ボタン）付近に講座一覧と同趣旨のアラートを表示する
2. If 表示中のドリルが現行より古い資料 version のものである, the Knowledge Drills frontend shall アラートを表示しない
3. The Knowledge Drills frontend shall アラートを講座の健康状態の通知として表示し、分析の実行可否の表現（ボタンの活性状態）とは独立させる
4. While 講座が要分析と判定されていない, the Knowledge Drills frontend shall ドリル管理画面の既存表示を変更しない

### Requirement 6: デモシードデータとの整合

**Objective:** As a デモ実施者, I want シードデータ投入直後の講座一覧で点灯と消灯の対比が成立する, so that デモ動画の1カット目で alerting を言葉ゼロで伝えられる

#### Acceptance Criteria

1. When デモシードデータ投入直後に講座一覧が表示される, the Knowledge Drills システム shall ハッカソン参加ガイド講座（未分析回答 4 件・平均スコア率 50%）にアラートバッジを表示する
2. When デモシードデータ投入直後に講座一覧が表示される, the Knowledge Drills システム shall 経費精算講座（現行 version の未分析回答 0 件・平均スコア率 90%）にアラートバッジを表示しない
3. The Knowledge Drills システム shall 上記の対比をシードデータの変更なしに成立させる
4. When 分析済み回答件数が未記録の分析済みドリルに採点済みの低スコア回答が追加され、追加後の未分析回答件数が閾値以上かつ現行 version 全体の平均スコア率が閾値未満になる, the Knowledge Drills システム shall その講座を要分析と判定してアラートバッジを表示する

### Requirement 7: ドキュメントの更新

**Objective:** As a ブログ読者・審査員, I want 画面の alerting とブログの主張が対応している, so that 「ドキュメントに DevOps を」の物語が実装で裏付けられていると分かる

#### Acceptance Criteria

1. The docs/blog.md shall DevOps 対応表に「アラート」と誤答閾値超過バッジの対応行を含む
2. The docs/blog.md shall 「次の周回」の記述を「検知は自動化した。次は起動（分析の自動実行）の自動化」の趣旨に更新した内容を含む
