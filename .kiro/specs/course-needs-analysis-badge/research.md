# Research & Design Decisions

## Summary
- **Feature**: `course-needs-analysis-badge`
- **Discovery Scope**: Extension（既存 FastAPI + React システムへの computed フィールド追加とバッジ表示）
- **Key Findings**:
  - FirestoreClient 抽象には field 単位の CAS / 条件付き更新プリミティブが存在しない。`run_transaction` は両実装にあるが、InMemory 実装は lock なしで callback を呼ぶだけ、Google 実装は ContextVar 参加型の本物のトランザクション。**FastAPI 同期エンドポイントは threadpool で並行実行されるため、InMemory でも実並行が起き得る** — InMemory の `run_transaction` を RLock で直列化した上で、条件付き更新を repository 層のトランザクション内 read-check-write で実装する（design レビューで「単一プロセス同期実行なので安全」という当初の見立てを訂正）
  - `course_service._summarize` のウォームパス（denormalized フィールドが揃っている場合）は drill run / 回答を読まない。needsAnalysis はリクエスト毎に現行 version の run と回答を読む必要がある（デモ規模の講座数・回答数では許容）
  - 閾値定数はモジュール定数の慣例（`EXPECTED_ANSWER_COUNT = 3`、`MAX_COURSE_MARKDOWN_CHARS`）がある。Settings（pydantic-settings）は存在するがサービス層へは注入されていない
  - DrillAdminPage は分析完了後に `api.getDrill` を再取得するため、分析実行でバッジが自然に消灯する。CourseListPage は当初マウント時のみ取得だったが、スコープ変更により講座一覧を監視・アラート面として扱い 15 秒ポーリングを追加（要件 4.4〜4.8）

## Research Log

### 条件付き更新（lazy 初期化 CAS / 単調非減少 watermark）の実現手段
- **Context**: 要件 2.4〜2.6 が「未記録の場合のみの初期化」「並行時に記録値を失わない」「単調非減少」を求める
- **Sources Consulted**: `backend/app/repositories/firestore_client.py`（Protocol 定義 line 25、InMemory line 48、Google line 97）、`backend/app/repositories/repositories.py`
- **Findings**:
  - `update_document` は両実装とも部分更新（merge）で、ドキュメント欠落時は `DocumentNotFound`
  - `create_document` は存在時 `DocumentAlreadyExists`（ドキュメント単位の set-if-missing はあるが field 単位はない）
  - `run_transaction(callback)`: Google 実装は `@firestore.transactional` + ContextVar で入れ子の repository 呼び出しが自動参加。InMemory 実装は callback を同期実行するだけ（隔離なし）。**FastAPI 同期エンドポイントは threadpool で並行実行されるため InMemory でも競合し得る** → `threading.RLock` で callback 実行全体を直列化する
  - `CourseRepository.increment_answer_count` はアプリ層の read-modify-write で非アトミック。CAS の先行事例なし（本 spec が新規パターンを導入）
- **Implications**: `DrillRepository` に `run_transaction` 内で read-check-write する専用メソッドは **initialize（lazy 初期化）の 1 つのみ**追加する（transaction 内で「field 欠落 かつ status ANALYZED」を再確認、`analyzedAnswerCount` のみの部分更新）。**分析完了時の watermark は既存の完了更新（全体 `update()`）に含めて単一書き込みで確定**する（記録失敗 = 分析失敗となり要件 2.1 を満たす）。単調性は「収集件数 ≥ 過去のいかなる記録値」の不変条件 + 初期化の status 再確認で保証（design.md の単調性の保証を正とする）

### needsAnalysis の計算経路と共有判定関数の置き場所
- **Context**: 要件 3.2 が講座一覧とドリル管理で同一判定ルール・同一判定を要求
- **Sources Consulted**: `course_service.py` `_summarize`（192-252）/ `_build_score_trend`（270-285）、`drill_service.py` `get_admin_drill`（145-184）
- **Findings**:
  - `_summarize` は warm path では Course の denormalized フィールドのみ参照。`_build_score_trend` に「run 一覧 → run 毎に GRADED 回答を集計」のパターンが既にある
  - `DrillService` は `course_repository`・`drill_repository`・`answer_repository` を保持し、`can_analyze` の computed 例（`graded_answer_count > 0`）と `_stored_answer_count` での Course 読み込み例がある
  - `Course.version` と `DrillRun.course_version` の比較で現行 version の run を特定できる
- **Implications**: 判定ロジックを `services/needs_analysis.py` に集約（純粋なルール関数 + repository を受け取る薄い評価関数）。CourseService と DrillService は同じ評価関数を呼ぶだけにし、判定の共同所有を作らない

### 閾値定数の管理方式
- **Context**: 要件 1.2（初期閾値 1 件 / 70%）。brief は「調整可能な定数」を要求
- **Sources Consulted**: `backend/app/config.py`（pydantic-settings、env prefix `KNOWLEDGE_DRILLS_`）、`answer_service.py:21`（`EXPECTED_ANSWER_COUNT = 3`）
- **Findings**: Settings はサービス層に注入されておらず、閾値のために `create_app` の配線変更が必要になる。モジュール定数の慣例が既にある
- **Implications**: `needs_analysis.py` のモジュール定数として定義（env 上書き不要、コード上の一箇所で調整可能）。Settings 配線は棄却

### フロントエンドの表示位置と再取得挙動
- **Context**: 要件 4.x / 5.x、`analysis-ui-declutter` の「実行可否を示す独立チップ禁止」制約
- **Sources Consulted**: `CourseListPage.tsx` `statusChips`（142-171）、`DrillAdminPage.tsx`（52-110, 140-147）、`components/common/`（StatusBanner 等）、`analysis-ui-declutter/requirements.md` Req 1-6
- **Findings**:
  - 講座カードのチップは `CourseSummary` の真偽値/enum から条件生成（「分析できます」は `drillStatus === 'ready' && answerCount > 0`）
  - DrillAdminPage は分析中 1 秒ポーリング + 分析完了後 refetch。バッジは分析実行後に自然消灯する
  - CourseListPage は当初マウント時のみ `api.listCourses()` する構成（ページ local state + `useEffect`）
- **Implications**: 一覧は chip パターンを流用（warning トーン、点灯時は「分析できます」を置換）。DrillAdmin は chip ではなく注記/バナー形式で表示し「実行可否チップ」と視覚的に区別（Req 5.3 と analysis-ui-declutter の両立）。ポーリングも既存の `useEffect` + local state 構成の延長で実装できる（下記 Design Decision 参照）

### シードデータとの整合
- **Context**: 要件 6.1〜6.3
- **Sources Consulted**: `demo_seed_data.py`（ハッカソン 127-218、経費精算 268-346）、`demo_seed_service.py`
- **Findings**: ハッカソン講座 = v1 run が READY・GRADED 4 件・平均 8/16 = 50%。経費精算講座 = v3 run が ANALYZED（`analyzed_answer_count` なし）・平均 90%
- **Implications**: 判定ルール（1 件以上 かつ 70% 未満）+「ANALYZED で field 欠落 → 未分析 0 件」でシード無変更のまま点灯/消灯が成立

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 共有判定モジュール + リード時計算（採用） | `needs_analysis.py` に純粋ルール関数と評価関数を置き、CourseService / DrillService から呼ぶ | 単一の判定所有者、永続化なし、既存レイヤ構造を維持 | 一覧取得毎に run/回答の読み取りが増える | デモ規模で許容。判定の重複実装を防ぐ |
| summary 永続化（update_summary 拡張） | 判定結果を Course doc に保存 | 読み取り高速 | 更新契機の管理漏れ = 誤表示、バックフィル要 | discovery 時に棄却済み |
| status 基準のみの簡易判定 | `status != ANALYZED` で未分析判定 | 実装最小 | 分析済み run への新規誤答を構造的に検知できない | requirements レビューで棄却済み |

## Design Decisions

### Decision: lazy 初期化は DrillRepository の専用 CAS メソッド + InMemory transaction の RLock 直列化で実装
- **Context**: 要件 2.4〜2.6（set-if-missing、並行安全、単調非減少）に対し、FirestoreClient に CAS プリミティブがなく、InMemory の `run_transaction` は隔離を持たない
- **Alternatives Considered**:
  1. FirestoreClient Protocol に汎用 CAS メソッドを追加 — 両実装の変更が必要で影響範囲が広い
  2. DrillRepository に用途特化メソッドを追加し `run_transaction` 内で read-check-write + InMemory の `run_transaction` を RLock で直列化 — 変更が repository 層に閉じる
- **Selected Approach**: 2。`initialize_analyzed_answer_count(drill_run_id, baseline)` は transaction 内で「field 欠落 かつ status が ANALYZED」を再確認してから書き込む（それ以外は no-op）。書き込みは `analyzedAnswerCount` のみの部分更新。`InMemoryFirestoreClient.run_transaction` は `threading.RLock` で callback 実行全体を排他する
- **Rationale**: FastAPI 同期エンドポイントは threadpool で並行実行されるため、InMemory でも実並行の read-check-write 競合が起き得る（design レビュー指摘）。Google 実装は `@firestore.transactional` のリトライで原子性を担保。status 再確認により、再分析（ANALYZING）中の初期化書き込みを排除し完了更新との競合窓を閉じる
- **Trade-offs**: RLock は InMemory の全 transaction を直列化するが、memory モードはデモ・テスト用途のため性能影響は無視できる。汎用 CAS は作らない（synthesis: 簡素化）
- **Follow-up**: ThreadPoolExecutor による実並行テストで「書き込みは 1 回のみ」を検証。Google 実装でネストした repository 呼び出しがトランザクションに参加することをコードレビューで確認

### Decision: 分析完了時の watermark は既存の完了更新に含めて単一書き込みで確定する
- **Context**: 要件 2.1 / 2.9。当初案（完了更新の直後に別途 field 書き込み + 失敗時は best-effort 成功）は「分析成功なのに未記録」を許し要件 2.1 に違反する（design レビュー指摘）
- **Alternatives Considered**:
  1. 完了更新後に別の field 単位書き込み、記録失敗は成功扱い — 2.1 違反（棄却）
  2. 完了時の `model_copy(update={...})` に `analyzed_answer_count` を含めて既存の全体更新 1 回で確定 — status・timeline・watermark が同時に確定し、書き込み失敗 = 分析失敗
- **Selected Approach**: 2。記録値は分析開始時に収集した `graded_answers` の件数（`collect_answers` 時点）
- **Rationale**: 「成功したのに未記録」が構造的に生じない（2.1）。既存の完了更新に field を足すだけなので既存遷移・タイムラインを維持（2.9）。単調性は「回答は削除されず採点済み件数は単調増加 → 収集件数は過去のいかなる記録値・baseline 以上」の不変条件と、lazy 初期化の status 再確認（ANALYZING 中は書かない）で保証（2.6）
- **Trade-offs**: 全体更新に含まれるため field 単位分離は完了経路では効かないが、完了更新は本 spec 以前からの既存挙動であり、要件 2.9 はこの形（既存遷移の維持 + field 追加）を明示的に許容している
- **Follow-up**: 既存の完了・失敗テストが変更なしで通ることを確認

### Decision: 閾値はモジュール定数（Settings 配線は不採用）
- **Context**: 要件 1.2。Settings はサービス層に届いていない
- **Selected Approach**: `needs_analysis.py` に `NEEDS_ANALYSIS_MIN_UNANALYZED = 1`、`NEEDS_ANALYSIS_SCORE_RATE_THRESHOLD = 0.7`
- **Rationale**: `EXPECTED_ANSWER_COUNT` の既存慣例に一致。env 上書きの要求はなく、配線変更を避けてスコープ最小化（synthesis: 簡素化）
- **Trade-offs**: 実行時変更不可。要求されたら Settings 化する

### Decision: 判定は「純粋ルール関数 + repository を受け取る評価関数」の2層
- **Context**: 要件 3.2（両画面で同一判定）と単体テスト容易性
- **Selected Approach**: `compute_needs_analysis(...)`（データのみ受け取る純粋関数）と `evaluate_course_needs_analysis(course, drill_repository, answer_repository)`（読み取り + 純粋関数呼び出し）を同一モジュールに置く
- **Rationale**: 閾値境界・run 状態別のルール検証を I/O なしでテストできる。CourseService / DrillService は評価関数を呼ぶだけで判定を共同所有しない（generalization: 判定 = 1 箇所）
- **Trade-offs**: なし（薄い層のみ）

### Decision: 講座一覧に 15 秒ポーリングを追加（シンプル版 setInterval 方式）
- **Context**: スコープ変更（オーナー指示）。講座一覧を監視・アラート画面として扱い、開いたままでも最新の要分析判定が見えるようにする。当初要件の「自動再取得を行わない」は削除
- **Alternatives Considered**:
  1. SSE / WebSocket / Firestore Listener — リアルタイムだが新規基盤が必要。毎回回答全件を再計算する現方式のままでは根本的な負荷改善にもならないため今回は不採用
  2. 可視性・フォーカス連動付きの `setTimeout` 連鎖ポーリング + 背景更新失敗表示 — 一度検討したが、デモ・ハッカソン規模には過剰としてシンプル版に置換
  3. 既存 `useEffect` 内の `setInterval`（15 秒）+ `fetching` ガード + `active` フラグ — 採用
- **Selected Approach**: 3。`COURSE_LIST_POLL_INTERVAL_MS = 15_000`。初回は即時取得、以降 15 秒毎に同じ `GET /api/courses` を再取得。前回取得が未完了なら開始しない。初回失敗は既存エラー画面、成功後の更新失敗は現在の一覧を静かに維持し次周期で自動再試行。アンマウント時に `clearInterval` + `active` フラグで完了済みリクエストからの setState を防止
- **Rationale**: 既存のページレベル API 呼び出し + local state 構成に合わせ、API クライアント・グローバル状態・新規 hook を変更しない最小差分。バックエンド変更なし
- **Trade-offs**: 非表示タブでも読み取りが続く（毎分 4 回/タブ）。デモ規模の Firestore 読み取り量（講座数 + run 数 + 対象回答数に比例）では許容。データ増加時の集計値永続化は将来の最適化として記載のみ
- **Follow-up**: Vitest fake timer（`advanceTimersByTimeAsync`）でポーリング・重複防止・アンマウント停止をテスト

### Decision: DrillAdmin のアラートはチップではなくバナー/注記形式
- **Context**: 要件 5.3 と `analysis-ui-declutter` Req 1-6（実行可否を示す独立チップの禁止）
- **Selected Approach**: 「回答を分析する」ボタン付近に warning トーンの注記（既存 StatusBanner 相当のスタイル）として表示。文言は講座の健康状態（例: 「低スコア回答が蓄積 — 分析推奨」）とし、`canAnalyze` とは無関係に判定のみで表示
- **Rationale**: チップ形式を避けることで「実行可否チップ」との視覚的混同を防ぎ、隣接 spec の制約と両立する

## Risks & Mitigations
- 一覧取得毎の run/回答読み取り増加 + 15 秒ポーリング（毎分 4 回/タブ） — デモ・ハッカソン規模で許容。将来スケール時は「採点・分析完了時に集計値を更新し一覧は講座ドキュメントのみ読む」方式へ移行できるよう判定を 1 モジュールに閉じ込める（今回は記載のみ）
- InMemory クライアントの run_transaction が隔離を持たない — `threading.RLock` で callback 実行全体を直列化し、ThreadPoolExecutor による実並行テストで検証（当初の「直列再現テストで十分」という方針は design レビューで棄却）
- 完了更新が stale オブジェクトからの全体更新である既存挙動 — lazy 初期化の status 再確認（ANALYZING 中は書き込まない）により、本 spec の field が巻き戻される interleaving を排除

## References
- GitHub issue #75 — 機能の背景と判定ルール案
- `.kiro/specs/course-needs-analysis-badge/brief.md` — discovery の決定事項
- `.kiro/specs/analysis-ui-declutter/requirements.md` Req 1-6 — DrillAdmin の表示制約
- `.kiro/specs/demo-course-seed/` — シードデータの所有 spec
