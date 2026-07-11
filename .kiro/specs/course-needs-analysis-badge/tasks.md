# Implementation Plan

- [ ] 1. Foundation: スキーマ拡張と並行制御基盤
- [x] 1.1 ドリルと両画面レスポンスのスキーマ拡張
  - DrillRun に分析済み回答件数（optional、未記録 = None）を追加し、講座一覧の講座要素とドリル管理レスポンスに要分析判定（真偽値、default false）を追加する
  - serialization は既存の camelCase 規約に自動追従させる（analyzedAnswerCount / needsAnalysis）
  - 完了条件: 既存のバックエンドテストが全て通り、両レスポンスに needsAnalysis が false で現れる
  - _Requirements: 3.1, 3.2_

- [x] 1.2 InMemory ストレージのトランザクション直列化
  - InMemory 実装の run_transaction を再入可能ロックで排他し、callback 実行全体を直列化する（FastAPI threadpool 並行実行対策）
  - Google 実装の挙動は変更しない
  - 完了条件: 複数スレッドから同時に run_transaction を呼ぶテストで callback が直列に実行される
  - _Requirements: 2.5_

- [ ] 1.3 分析済み回答件数の lazy 初期化用の条件付き更新
  - トランザクション内で「件数が未記録 かつ 分析済み status」を再確認した場合のみ baseline を書き込む repository メソッドを追加する（それ以外は no-op）
  - 書き込みは分析済み回答件数 field のみの部分更新とし、他 field（status・タイムライン等）を変更しない
  - 実並行テスト: ThreadPoolExecutor で同一ドリルへの初期化を多重実行しても書き込みが 1 回のみ / 分析実行中のドリルには書き込まない / 記録済みの値を変更しない
  - 順序組み合わせテスト: 初期化 → 完了更新（汎用 update で模擬）で完了更新の値が有効になる / 完了更新 → 初期化で記録済みの値が変更されない（watermark 非後退）
  - 完了条件: 上記の並行・条件・順序テストが test_repositories.py で通る
  - _Requirements: 2.4, 2.5, 2.6, 2.8_

- [ ] 2. Core backend: 判定ロジックと watermark 記録
- [ ] 2.1 (P) 要分析判定モジュール
  - 判定閾値（未分析 3 件以上、平均スコア率 70% 未満）を調整可能なモジュール定数として一元定義する
  - 純粋ルール関数: 現行資料 version の run と回答から判定する。採点済み回答のみ集計、平均は採点済み全体、run 状態別の未分析算入（未実施 = 全件 / 分析実行中・生成中・生成失敗 = 0 件 / 分析済み = 採点済み − 記録値で 0 未満クランプ / 記録欠落 = 0 件）、採点済み 0 件・算出不能は偽
  - repository から読み込んで純粋関数へ委譲する評価関数を同モジュールに置く（書き込みなし）
  - 完了条件: 閾値境界（2/3 件、70%/69%）と run 状態の全分岐を固定する単体テスト（test_needs_analysis.py）が通る
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_
  - _Boundary: NeedsAnalysis_

- [ ] 2.2 (P) 分析成功時の分析済み件数の一体記録
  - 分析開始時に収集した採点済み回答の件数を、既存の完了更新（ANALYZED 遷移 + タイムライン）に含めて単一書き込みで確定する
  - 完了書き込みが失敗した場合は分析を成功として返さない（既存エラー経路）。失敗経路（READY 戻し）では件数を更新しない
  - 完了条件: 成功時に収集件数が記録される / 分析中に追加された回答が記録値に含まれない / 失敗経路で件数不変 / 既存の分析テストが変更なしで通る（test_analysis_service.py）
  - _Requirements: 2.1, 2.2, 2.3, 2.6, 2.9_
  - _Boundary: AnalysisService_

- [ ] 2.3 (P) 回答受付時の lazy 初期化の組み込み
  - 分析済み status かつ件数未記録のドリルへの回答受付時、回答保存の前に保存前時点の採点済み件数で初期化する（権威判定は repository のトランザクション内再確認）
  - 初期化の例外は伝播させ、回答を保存しない
  - 初期化失敗時に drill_run_id 付きの warning ログを出力する（観測可能性）
  - 完了条件: 初回回答で初期化・2 回目は no-op / 初期化失敗で回答が保存されない（test_answer_service.py）
  - _Requirements: 2.4, 2.7_
  - _Boundary: AnswerService_
  - _Depends: 1.3_

- [ ] 3. Integration backend: 両画面レスポンスへの判定反映
- [ ] 3.1 (P) 講座一覧レスポンスへの判定設定
  - 講座サマリー組み立て時に評価関数を呼び要分析判定を設定する（永続化しない、リクエスト毎に最新状態を反映）
  - シード整合: 投入直後の一覧でハッカソン参加ガイド講座 = 真 / 経費精算講座 = 偽（シード定義に差分なし）を統合テストで固定する（test_courses_api.py）
  - 完了条件: 上記シード対比テストが通る
  - _Requirements: 1.11, 3.1, 6.1, 6.2, 6.3_
  - _Boundary: CourseService_
  - _Depends: 2.1_

- [ ] 3.2 (P) ドリル管理レスポンスへの判定設定と version ガード
  - 表示中ドリルが現行資料 version の場合のみ評価関数で判定を設定し、過去 version は偽固定とする
  - 一覧と同一の判定ルール（同じ評価関数）を使い、判定ロジックを重複実装しない
  - 完了条件: 現行 version の管理レスポンスに評価関数の判定結果（当該講座の期待真偽値）が現れ、過去 version で偽になるテストが通る（test_drills_api.py）
  - _Requirements: 1.11, 3.2, 3.3_
  - _Boundary: DrillService_
  - _Depends: 2.1_

- [ ] 3.3 legacy 分析済みドリルの検知シナリオ統合テスト
  - 件数未記録の分析済みドリルへ採点済み低スコア回答を 3 件追加し、未分析件数が閾値以上かつ平均スコア率が閾値未満になった時点で一覧の判定が真になることを検証する
  - 完了条件: 上記シナリオの統合テストが test_courses_api.py で通る（3.1 完了後に着手するため同ファイル編集の競合なし）
  - _Requirements: 6.4_
  - _Depends: 2.3, 3.1_

- [ ] 4. Core frontend: バッジ表示とポーリング
- [ ] 4.1 API 型の拡張と講座カードのアラートチップ
  - CourseSummary / DrillAdmin 型に needsAnalysis を追加する
  - statusChips: 判定が真なら warning チップ「低スコア回答が蓄積 — 分析推奨」を出し「分析できます」チップを生成しない。偽なら既存表示不変
  - 完了条件: チップ表示・置換・非点灯不変のテスト（CourseListPage.test.tsx）が通る
  - _Requirements: 4.1, 4.2, 4.3_

- [ ] 4.2 講座一覧の 15 秒ポーリング
  - 既存 useEffect 内に setInterval（15 秒）+ fetching ガード + active フラグを実装する。初回は即時取得
  - 更新失敗時の state 判定は functional update に固定する（ready なら据え置き、初回失敗のみ failed）
  - アンマウント時に clearInterval し、完了済みリクエストから state を更新しない
  - 完了条件: fake timer テスト（即時取得 / 15 秒後の再取得とバッジ更新 / 失敗時の一覧維持 / 重複取得防止 / アンマウント後停止）が通る
  - _Requirements: 4.4, 4.5, 4.6, 4.7, 4.8_

- [ ] 4.3 (P) ドリル管理画面のアラートバナー
  - 「回答を分析する」ボタン付近に warning バナー（チップ形式ではない注記）を判定が真の場合のみ表示する
  - 表示条件は判定のみ（canAnalyze と独立）。偽なら既存表示不変
  - 完了条件: バナー表示 / canAnalyze=false でも表示 / 偽で非表示のテスト（DrillAdminPage.test.tsx）が通る
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Boundary: DrillAdminPage_
  - _Depends: 4.1_

- [ ] 5. Validation & docs
- [ ] 5.1 ブログ記事の DevOps 対応表と「次の周回」更新
  - 対応表に「アラート | 誤答閾値超過バッジ」の行を追加する
  - 「次の周回」を「検知は自動化した。次は起動（分析の自動実行）の自動化」の趣旨に更新する
  - 完了条件: docs/blog.md に両変更が含まれる
  - _Requirements: 7.1, 7.2_

- [ ] 5.2 全体検証
  - backend: pytest、ruff、mypy を実行する
  - frontend: test、typecheck、lint、build を実行する
  - requirements 1〜7 の完了条件と、シードデータが未変更であることを確認する
  - 完了条件: 必須チェックがすべて成功する
  - _Requirements: 6.3_
  - _Depends: 3.3, 4.2, 4.3, 5.1_

- [ ]* 5.3 E2E: シード対比の確認
  - Playwright の既存シナリオに、シード投入後の講座一覧で 2 講座の点灯/消灯対比を確認するアサーションを追加する（6.1、6.2 は 3.1 の統合テストで担保済みのため任意）
  - 完了条件: E2E がシード投入後の 2 講座で点灯/消灯を検証して通る
  - _Requirements: 6.1, 6.2_
  - _Depends: 4.1_
