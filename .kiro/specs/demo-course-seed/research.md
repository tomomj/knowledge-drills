# Research & Design Decisions — demo-course-seed

## Summary
- **Feature**: `demo-course-seed`
- **Discovery Scope**: Extension(backend の投入機構・削除 API・一覧応答拡張 + frontend 講座一覧)
- **Key Findings**:
  - Firestore は全てトップレベルコレクション(courses / course_revisions / drill_runs / answers / patches / share_tokens / users)で、講座一覧は course ドキュメントの**非正規化済み要約フィールド**だけで組み立てられる(N+1 回避がテストで担保されている)
  - `FirestoreClient` Protocol に **delete 系メソッドが存在しない**(コードベース全体で削除実装ゼロ)。講座削除はクライアント抽象からの新設になる
  - `users/{uid}` ドキュメント(`GET /api/me` で upsert)が存在し、シード済みフラグの置き場として使える
  - metrics は drill_run ごとに answers を集計して算出するため、一覧行のスパークラインを素朴に一覧時計算すると N+1 になる。一方 `_summarize` には「不足フィールドを読み取り→書き戻す」バックフィルの既存パターンがある

## Research Log

### 永続化レイアウトと一覧の組み立て
- **Context**: シードが書き込むべきドキュメントの正確な形と、一覧応答拡張の影響範囲
- **Sources Consulted**: `backend/app/repositories/repositories.py`、`schemas.py`、`course_service.py:88-223`、`tests/test_courses_api.py:52-84`
- **Findings**:
  - course ドキュメントに `ownerUserId` と要約フィールド(`latestDrillStatus` / `answerCount` / `latestPatchStatus` / `latestDrillRunId` / `latestPatchId`)が非正規化保存されている。一覧は `ownerUserId==` クエリ 1 回 + バックフィル(不足時のみ)で構成
  - revisions は `course_revisions/{courseId}:{version}` に**全文スナップショット**で保存され、`CourseRepository.create/update` が自動記録する。diff は取得時に `build_unified_diff` でオンザフライ生成
  - drill_run は `share_token` のみ保持し、`share_tokens/{token}` が逆引きを担う。`scoreSummary` / `canAnalyze` / `shareUrl` は応答時に answers 集計から導出される
  - patch に `appliedAt` は存在しない。適用済み patch は `status: applied` で表現される
- **Implications**: シードは「repository の既存 create/update を順に呼ぶ」だけで revisions・要約フィールドが自然に整う。ドキュメントを手組みするより既存経路を通す方が schema 整合(R6.4)を保ちやすい

### シード済みフラグとトリガー位置
- **Context**: R1.1(一覧取得と同じ応答に含める)・R1.2-1.3(冪等・再投入なし)の実現方法
- **Sources Consulted**: `auth.py`、`firebase_auth_client.py:63-73`、`user_service.py:19-31`、`routes/users.py`
- **Findings**:
  - オーナー uid は `require_current_user` で全 route に供給される(auth_mode=none では固定 `local-owner`)
  - `users/{uid}` は `GET /api/me` アクセス時に upsert される。ただし講座一覧の取得前に `/api/me` が呼ばれる保証はない
- **Implications**: シード判定は講座一覧のフローに置き、フラグは `users/{uid}` の追加フィールド(`demoSeededAt`)に置く。users ドキュメント不在でも `set(merge)` 相当の upsert で書けるようにする

### 削除機構の不在
- **Context**: R5(講座削除)の実装コスト見積り
- **Sources Consulted**: `firestore_client.py`(Protocol とInMemory / Google 両実装)、`repositories.py`
- **Findings**: `delete_document` が Protocol にも両実装にも存在しない。関連データは course を親に持つが物理的にはトップレベルコレクションに分散しているため、削除はコレクション横断のカスケードになる
- **Implications**: `delete_document` を Protocol・InMemory・Google の 3 箇所に新設し、各 Repository に `delete` を追加する。カスケード順序は「子 → 親」(share_tokens → answers → drill_runs → patches → revisions → course)とし、途中失敗時は course が残る(=一覧に見え、再試行可能)側に倒す

### Design review 指摘への対応(2026-07-08)
- **Context**: 初版 design のレビューで 3 件の Important と 1 件の Suggestion
- **Findings / 対応**:
  - `user_service.upsert_current_user` が user ドキュメントを丸ごと作り直すため、`/api/me` アクセスで `demo_seeded_at` が消え、削除後の再投入(R1.3 違反)が起き得る → user_service を Modified Files に追加し、既存フィールド保持を明記。seed → /api/me → 削除 → 一覧のテストを追加
  - 削除カスケードの列挙契約が不足(`PatchRepository.list_by_course` が存在しない、`ShareTokenRepository.delete` 未定義) → Repository 層の列挙・削除契約表を design に追加
  - `scoreTrend` のスケールが metrics と一致する保証がない → `_build_metrics_run` と同一の計算規則(graded totalScore の raw 平均 / questions の maxScore 合計)を定義し、`/metrics` との一致テストを追加
  - 二重削除の意味論が矛盾(owned lookup は 404、テストは「冪等」) → API は再 DELETE で 404、「冪等」は repository レベルの delete no-op に限定と決定
- **Implications**: tasks 生成前に解消済み

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 一覧時にスパークライン用スコアをオンザフライ集計 | list_courses で drill_runs + answers を読む | 実装最小 | 講座×run×answers の N+1。既存の「一覧は course ドキュメントのみで構成」パターンとテストを壊す | 不採用 |
| score trend の非正規化 + バックフィル(採用) | course ドキュメントに `scoreTrend` を保存。採点完了時に更新、欠損時は `_summarize` のバックフィルで補完 | 既存の要約フィールドと同じパターン。一覧の読み取り量を維持 | 採点フローに 1 箇所更新が増える | `_summarize` のバックフィル前例(course_service.py:167-195)に従う |
| frontend から講座ごとに metrics API を N 回呼ぶ | クライアント側 N+1 | backend 変更なし | 講座数に比例して一覧が遅くなる。R4.7(応答に含める)に反する | 不採用 |

## Design Decisions

### Decision: シードは講座一覧フロー内で同期実行し、フラグを先にトランザクションで確保する
- **Context**: R1.1 は「同じ一覧応答に含める」を要求。並行リクエストによる二重投入も防ぎたい
- **Alternatives Considered**:
  1. データ書き込み後にフラグを立てる(失敗時に再試行されるが、並行時に二重投入)
  2. フラグを先にトランザクションで確保(claim)してからデータを書く(二重投入なし。途中失敗時は部分データが残り自動再試行されない)
- **Selected Approach**: 2。`users/{uid}.demoSeededAt` を run_transaction で「未設定なら設定」し、確保できた場合のみ固定データを書き込む
- **Rationale**: デモ用途では「二重に見える」方が「稀に部分的」より実害が大きい。固定データの書き込みは外部依存がなく失敗確率が低い
- **Trade-offs**: 書き込み途中の失敗で不完全なデモ講座が残り得る(一覧取得自体は R1.6 により成功)
- **Follow-up**: シード失敗時に警告ログを出し、手動リカバリ(講座削除)を可能にしておく

### Decision: シードデータは repository の既存経路(create → update)を通して構築する
- **Context**: R3.1(v1→v3 の履歴)と R6.4(既存 schema 検証との整合)
- **Selected Approach**: デモ講座②は `CourseRepository.create`(v1)→ `update` ×2(v2, v3)の順で書き、revisions を自然に記録する。drill_run / answers / patch / share_token も既存 Repository と Pydantic モデル経由で書く
- **Rationale**: ドキュメント直書きだと camelCase alias・revision 記録・要約フィールドの整合を手動維持することになる。モデル経由なら schema 変更に追従する
- **Trade-offs**: シードコードが repository 呼び出しの列になる(データ定義とロジックを分離して可読性を保つ)
- **Follow-up**: デモ教材①の `sourceEvidence.excerpt` が教材本文に文字列一致することをテストで検証する(実在チェックと同型)

### Decision: スパークライン用スコアは course ドキュメントの `scoreTrend` に非正規化する
- **Context**: R4.1(一覧行の推移表示)と R4.7(応答に含める)。一覧の N+1 回避パターンがテストで固定されている
- **Selected Approach**: `scoreTrend: [{courseVersion, averageScore, maxScore}]` を course ドキュメントに保存。更新点は (a) 採点完了時(answer_service が該当 run の平均を再計算)、(b) シード時(固定値)、(c) `_summarize` のバックフィル(answerCount>0 なのに欠損の場合のみ集計して書き戻す)
- **Rationale**: 既存の要約フィールド群と同じライフサイクル・同じバックフィル前例に載せる
- **Trade-offs**: 採点フロー(answer_service)に更新箇所が 1 つ増える
- **Follow-up**: 採点完了 → 一覧に反映、をテストで検証する

### Decision: 講座削除は「子 → 親」の順で逐次削除し、course を最後に消す
- **Context**: R5.1-5.2。削除はコレクション横断カスケードで、トランザクションの書き込み上限や途中失敗を考慮する
- **Selected Approach**: share_tokens → answers → drill_runs → patches → course_revisions → course の順に逐次削除。course が最後なので、途中失敗時は講座が一覧に残り再試行できる。存在しないドキュメントの削除は no-op(冪等)
- **Rationale**: 逆順(course 先)だと失敗時に孤児データが不可視のまま残る。子先なら再試行で収束する
- **Trade-offs**: 削除全体はアトミックではない(ユーザー観測上は「もう一度削除」で解決)
- **Follow-up**: share_token 削除により学習者の共有 URL が即時無効になること(R5.2)をテストで検証

### Decision: 一覧のミニ折れ線は CourseListPage 内のページローカル実装にする
- **Context**: 実装済みの `ScoreSparkline` が `CourseEditorPage` 内に存在する(score-progression-ui の成果物)
- **Alternatives Considered**:
  1. `components/common` へ抽出して両ページで共用(CourseEditorPage の変更が必要)
  2. CourseListPage 内に一覧向けのミニ変種を定義(SVG 約 20 行の重複)
- **Selected Approach**: 2
- **Rationale**: 2 つの表示はサイズ・情報量が異なり(一覧: 130×30 装飾なし / 編集: 64px 高 + 面塗り + 端点強調)、共通化は props 分岐を生む。完成済み spec の成果物ファイルへの変更も避けられる
- **Trade-offs**: 小さな SVG 重複。3 箇所目が必要になったら抽出する
- **Follow-up**: なし

### Decision: 削除 UI は講座管理(Course Editor)に置き、2 段階クリックで確認する
- **Context**: R5.3(確認ステップ)。一覧行に置くと誤タップ導線になる
- **Selected Approach**: 講座管理のサイド(講座の状態カード下)に危険色ボタンを置き、1 回目のクリックで「本当に削除する」に変わる 2 段階確認にする。ブラウザ標準ダイアログは使わない(テスト容易性)
- **Trade-offs**: CourseEditorPage への小変更が入る(本 spec の所有として File Structure Plan に明記)
- **Follow-up**: 削除成功後は講座一覧へ遷移する

## 実 Agent 歩留まり確認(2026-07-12)

- **Runtime**: Vertex AI `gemini-3.1-flash-lite`、`GOOGLE_CLOUD_LOCATION=global`
- **Input**: 通常生成契約へ揃えたハッカソンデモ(3問・各4点)と初期採点済み回答2件
- **Grading result**: seed の q1 を実採点し、`questionId=q1 / score=4 / maxScore=4` の schema-valid 応答を確認
- **Analysis result**: 実分析で教材の「提出物」セクションに、デモURLの公開状態・認証不要条件が欠けていることを Failure Signal として検出
- **Patch result**: 実 document patch agent が、公開設定と認証情報の記載要件を「提出物」へ追記するパッチを提案。`patchedMarkdown` に「認証」が含まれることを確認
- **Conclusion**: seed の採点・分析入力は Agent schema を通過し、意図した教材ギャップからパッチ提案まで到達した

## Risks & Mitigations
- デモ教材①(ハッカソン概要)の要約が公式文言と酷似する → 構成・表現を独自に書き下ろし、転載を避ける(R2.2)。レビュー時に目視確認
- 実 agent がデモ講座①の分析で意図した教材ギャップを見つけない → 初期回答 2 件の過半数を記載不足箇所に集中させ、次の回答で自動分析の3件閾値へ到達させる(R2.5)。提出前に実際に分析を回して歩留まりを確認する
- シード途中失敗による部分データ → claim 方式の trade-off として許容し、警告ログ + 講座削除でリカバリ可能にする
- 削除カスケードの途中失敗 → 子→親順で再試行可能。冪等な delete
- `scoreTrend` バックフィルが一覧の N+1 回避テストと衝突 → バックフィルは「欠損時のみ」の既存前例と同条件にし、通常時は course ドキュメントのみで構成されることをテストで維持

## References
- `.kiro/specs/demo-course-seed/requirements.md` — 本設計の入力
- `.kiro/specs/score-progression-ui/` — スコア推移カード(実装済み、デモ講座②が最初から表示させる対象)
- `.kiro/specs/google-login-owner-scope/` — ownerUserId 認可規則(削除 API が従う)
- `backend/tests/test_courses_api.py:52-84` — 一覧の N+1 回避を担保する既存テスト
