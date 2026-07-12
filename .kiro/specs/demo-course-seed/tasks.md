# Implementation Plan

- [x] 1. ドキュメント削除の抽象を FirestoreClient に追加する
  - Protocol・InMemory・Google の 3 箇所に delete_document を追加(存在しない文書は no-op)
  - InMemory / Google 両実装の削除・no-op 挙動を単体テストで検証し green になっていること
  - _Requirements: 5.1_
  - _Boundary: FirestoreClient_

- [x] 2. 削除カスケードとシード claim に必要な Repository 契約を追加する
  - 各 Repository の delete、PatchRepository.list_by_course(新設)、ShareTokenRepository.delete(token)、course_revisions の courseId 列挙+delete を追加
  - UserRepository にシード済みフラグ(demoSeededAt)の部分更新(他フィールドを壊さない update)を追加
  - 追加した列挙・削除・部分更新メソッドの repository テストが green になっていること
  - _Requirements: 5.1, 1.2_

- [x] 3. (P) スキーマにデモ・スコア要約フィールドを追加する
  - Course に scoreTrend(courseVersion / averageScore / maxScore、metrics と同一スケール)と isDemo(default false)、CourseSummary に同フィールド、UserProfile に demoSeededAt を追加(すべて追加のみで後方互換)
  - 既存 API 応答のシリアライズが変わらないこと(追加フィールドは null / false 既定)をテストで確認
  - _Requirements: 4.7, 4.4, 1.2, 6.3_
  - _Boundary: schemas_

- [x] 4. 講座削除 API を追加する
  - CourseService.delete_course: 所有者検証(他オーナー・存在しない講座は 404)、share_tokens → answers → drill_runs → patches → course_revisions → course の順で逐次削除
  - DELETE /api/courses/{course_id} route を追加
  - 削除後に一覧・course/drill/patch 取得が 404、share token 解決が無効、再 DELETE が 404 になることをテストで検証し green
  - _Requirements: 5.1, 5.2, 5.4_
  - _Depends: 1, 2_

- [x] 5. scoreTrend の非正規化を実装する
- [x] 5.1 採点完了時の scoreTrend 更新
  - 回答の採点完了時に該当 drill run の graded 回答から metrics と同一規則(totalScore raw 平均 / questions の maxScore 合計)で平均を再計算し、course の scoreTrend の該当 courseVersion エントリを更新する
  - 採点完了後の一覧応答に更新済み scoreTrend が含まれることをテストで検証
  - _Requirements: 4.7_
  - _Depends: 3_

- [x] 5.2 一覧応答への反映とバックフィル
  - CourseSummary に scoreTrend / isDemo を反映。answerCount > 0 かつ scoreTrend 欠損の講座のみ metrics と同じ集計で書き戻すバックフィルを _summarize に追加
  - 同一講座で GET /metrics の runs と CourseSummary.scoreTrend が一致することをテストで検証
  - 通常時(欠損なし)は一覧が course ドキュメントのみで構成される既存 N+1 回避テストを green のまま維持
  - _Requirements: 4.7, 4.4, 6.3_
  - _Depends: 3_

- [x] 6. デモシードを実装する
- [x] 6.1 (P) 固定デモデータの定義
  - デモ講座①: ハッカソン概要の独自要約教材(転載なし、意図的な記載不足 1 箇所)、通常生成と同じ設問 3 問・各4点(sourceEvidence.excerpt が教材本文に文字列一致)、採点済み回答 2 件(次の回答で自動分析の3件閾値へ到達、誤答の過半数が記載不足箇所関連、平均 6 点 / 12 点)
  - デモ講座②: 経費精算教材 v1→v3 の 3 版、通常生成と同じ設問3問・各4点のバージョン別採点済み run 3 件(平均 5.4→8.7→10.8 / 12 点、metrics と同一スケール)、v2→v3 の applied パッチ(failure_signals・完了済みタイムライン・build_unified_diff による diffText)
  - 両講座の scoreTrend 固定値(metrics と同一スケール)と isDemo=true をデータ定義に含める
  - excerpt の教材一致・スコア平均の定義値をアサートする data テストが green になっていること
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.5, 6.4_
  - _Boundary: demo_seed_data_
  - _Depends: 3_

- [x] 6.2 DemoSeedService と claim(user_service 統合を含む)
  - 講座 0 件かつ未シードの判定、users/{uid}.demoSeededAt のトランザクション claim(タスク 2 の部分更新を使用)、repository 経由(course create→update×2、drill_runs、share_tokens、answers、patches)での投入
  - 投入時に各講座の scoreTrend 固定値と isDemo を course ドキュメントへ書き込む
  - user_service.upsert_current_user が既存 demo_seeded_at を保持するよう修正(境界をまたぐ統合修正として本タスクが所有)
  - 講座ありオーナー・claim 済みオーナーに投入されないこと、投入データの ownerUserId がリクエスト uid であることをテストで検証
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 6.1_
  - _Depends: 2, 6.1_

- [x] 6.3 講座一覧フローへの統合
  - 一覧 route の前段で ensure_seeded を呼び、DI を main に配線。投入失敗は警告ログを出して一覧取得を継続
  - 初回一覧取得でデモ講座 2 件が同じ応答に含まれることをテストで検証
  - 続けてデモ講座①のドリル確認(DrillAdminResponse)を取得すると canAnalyze が true であること、②の metrics が上昇する 3 run を返す(スコア推移カードの表示条件成立)ことをテストで検証(canAnalyze は一覧応答のフィールドではない点に注意)
  - seed → GET /api/me → デモ講座削除 → 一覧再取得で再投入されないことをテストで検証
  - 投入処理を失敗させても一覧が 200 を返すことをテストで検証
  - _Requirements: 1.1, 1.6, 2.6, 3.4_
  - _Depends: 4, 6.2_

- [x] 7. frontend の一覧ダッシュボード化と削除 UI
- [x] 7.1 (P) API 型とクライアントの拡張
  - CourseSummary 型に scoreTrend / isDemo を追加し、deleteCourse メソッドを追加
  - typecheck が green になっていること
  - _Requirements: 4.7, 5.1_
  - _Boundary: frontend api_
  - _Depends: 3_

- [x] 7.2 講座一覧の行表示と案内バナー
  - scoreTrend の**要素(scored run)が 2 件以上**の行にミニ折れ線(ページローカル SVG、支援技術向け代替ラベル)と「平均 X.X → Y.Y」要約を表示。要素 1 件以下・欠損時は非表示で行表示を維持(平均点の値による条件ではない)
  - isDemo 行にデモチップ、drillStatus ready かつ answerCount > 0 の行に分析誘導バッジ、デモ講座があるとき上部に案内バナーを表示
  - 平均点が低くても要素 2 件なら表示され、要素 1 件なら高得点でも非表示になることをテストで検証し green になっていること
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.8_
  - _Depends: 7.1_

- [x] 7.3 講座管理の削除ボタン
  - サイドに危険色ボタンを追加し、1 回目クリックで「本当に削除する」に変わる 2 段階確認。確定で deleteCourse を呼び、成功時は講座一覧へ遷移、失敗時は既存エラーバナー表現
  - 2 段階確認・成功遷移・失敗表示がテストで検証され green になっていること
  - _Requirements: 5.3_
  - _Depends: 7.1_

- [x] 8. 統合検証
- [x] 8.1 e2e テストの追加
  - 削除した講座の共有 URL を開くと無効な共有 URL 表示になるシナリオを追加
  - learner 画面にデモ講座でも rubric / idealAnswer が表示されないことを確認
  - 追加シナリオが green になっていること
  - _Requirements: 5.2, 6.2_
  - _Depends: 6.3, 7.3_

- [x] 8.2 全体回帰
  - backend(pytest / ruff / mypy)と frontend(typecheck / lint / test / build)がすべて green になっていること
  - _Requirements: 6.3_

- [x] 8.3 実分析の歩留まり確認
  - デモ講座①で実 agent の分析を 1 回実行し、教材の記載不足に言及するパッチが提案されることを確認する(agent 出力は非決定的なため自動テストではなく手動確認)
  - 確認結果(実行日時・提案内容の要旨)を spec の research.md に追記して記録すること
  - _Requirements: 2.7_
  - _Depends: 6.3_
