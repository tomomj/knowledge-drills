# Brief: course-needs-analysis-badge

## Problem

講座オーナーは、誤答テレメトリが貯まっていても「気が向いたときに分析ボタンを押す」手動検知しかできない。
DevOps の絵で言うと monitoring はあるが alerting がない状態で、どの資料が悲鳴を上げているかは
講座一覧を開いただけでは分からない（GitHub issue #75）。

## Current State

- 誤答（回答）は Firestore に貯まり、分析は講座オーナーが手動で起動する。
- 講座一覧（`GET /api/courses`）には `drillStatus` / `answerCount` / `patchStatus` / `scoreTrend` などの
  computed フィールドが既にあるが、「分析が必要か」を示すシグナルはない。
- **現行モデルでは「未分析回答」を判定できない**: `ANALYZED` の drill run も回答受付を継続でき
  （`drill_status_policy.py` の `DISTRIBUTABLE_DRILL_STATUSES` に `ANALYZED` を含む）、回答追加時に
  run status は変化せず、回答（`AnswerSubmission`）にも run（`DrillRun`）にも分析済み件数の記録がない。
  `status != ANALYZED` 基準では、分析完了後に追加された新しい誤答を検知できない。
- `get_course` は `_summarize` を通らず素の `Course` を返すのみ。DrillAdminPage は `CourseDetail` ではなく
  `DrillAdminResponse`（`DrillAdmin` 型）を読む別契約。
- 講座一覧には既に「分析できます」チップ（`drillStatus === 'ready' && answerCount > 0`、demo-course-seed 所有）がある。
- シードデータは対比が成立する値になっている:
  - ハッカソン参加ガイド講座: 現行 version(v1) の run は `READY`、未分析回答 4 件、平均スコア率 50%（8/16 点）
  - 経費精算講座: v1〜v3 の run すべて `ANALYZED`、現行 version(v3) の未分析回答 0 件、平均スコア率 90%

## Desired Outcome

- 講座一覧を開いた瞬間に「健康な講座」と「アラート中の講座」の対比が分かる。
- 判定ルール: `needsAnalysis = 現行 version への未分析回答が N 件以上（初期値 1）かつ 現行 version の平均スコア率が閾値未満（初期値 70%）`。
  閾値は実装時に調整可能な定数とする。
- シードデータとの整合: 経費精算講座 → バッジ消灯、ハッカソン参加ガイド講座 → バッジ点灯（シードデータ自体は無変更のまま成立させる）。
- docs/blog.md が「monitoring → alerting → human triage → human gate」の形を画面で裏付ける記述になる。
- デモ動画撮影（1カット目: 2講座並んで片方が警告）より前にマージされる。

## Approach

**リード時計算 + 分析完了時の最小メタデータ記録**。

1. **未分析件数の判定基盤（分析完了処理 + 回答受付への最小追記）**: 分析が成功した時点で、その run の
   `analyzed_answer_count` を `DrillRun` に記録する。snapshot の値は**完了時の再集計ではなく、
   分析開始時に収集して実際に分析へ渡した GRADED 回答集合の件数**（`analysis_service.py` の
   `collect_answers` 時点の `graded_answers` 件数）とする。分析中も回答受付は可能なため、
   完了直前に届いた回答を分析済み扱いしないための措置。未分析件数は
   `gradedAnswerCount - analyzedAnswerCount` で導出する。
   **既存 run の lazy 初期化**: `ANALYZED` かつ field 欠落の run への最初の回答受付時に、
   新規回答を保存する前の GRADED 件数を baseline として一度だけ `analyzed_answer_count` に記録する。
   これにより既存 run もデプロイ後の新規回答を検知でき、一括バックフィルとシードデータ変更は不要のまま。
   読み取り時に field が欠落している run（= デプロイ後に回答が来ていない既存 run）は「未分析 0 件」として扱う。

   **`analyzed_answer_count` 更新の並行性制約**（lazy 初期化と分析完了が並行し得るため）:
   - lazy 初期化は「field が欠落している場合のみ書き込む」atomic な compare-and-set とする。
     読み取り→計算→無条件書き込みの分離は、並行する分析完了の値（watermark）を古い baseline で
     巻き戻す競合を生むため許容しない
   - 更新は `analyzedAnswerCount` field のみの部分更新とする。既存 `DrillRepository.update()` は
     run 全体を `set_document` で上書きするため流用しない（status / analysis_timeline を巻き戻す危険がある）
   - `analyzed_answer_count` は単調非減少（watermark）とし、いかなる書き込みでも既存値より小さい値へ後退させない
   - lazy 初期化に失敗した場合は回答を保存せず失敗させる（field 欠落のまま回答だけ増える
     「検知不能状態」を作らない）
2. **needsAnalysis はリード時純粋計算**: レスポンス生成時に現行 version の run と回答を集計して
   `needsAnalysis: bool` を返す。判定ロジックは service 層の共有判定関数に置き、
   `CourseSummary`（一覧）と `DrillAdminResponse`（ドリル管理）の 2 契約から呼ぶ。
   needsAnalysis 自体は永続化しない。

選定理由: `status != ANALYZED` のみの判定は「分析済み run への新規誤答」を構造的に検知できず、
判定ルールの意味論とズレるため、分析完了時の件数記録を唯一のパイプライン接点として明示的に許容する。
エージェント側（ADK / プロンプト / 分析内容）は無変更。needsAnalysis の永続化は更新契機の管理と
誤表示リスクを増やすため採らない（棄却案: `update_summary` パターンでの永続化、status 基準のみの簡易判定）。

講座一覧は監視・アラート面として扱い、既存 `GET /api/courses` の **15 秒間隔ポーリングを In scope** とする
（重複取得防止・アンマウント時停止を含む。ドリル管理画面への新規ポーリング追加はしない）。
WebSocket / SSE / Firestore Listener 等のリアルタイム通信は Out of scope。

### 判定ルールの境界条件（requirements で固定する前提値）

- 件数・平均スコア率とも **`GRADED` の回答のみ**を集計対象とする（採点中・採点失敗・スコアなしは除外）。
- 未分析件数の run 別内訳: `READY` → graded 全件、`ANALYZING` → 0 件（分析＝triage 実行中のため点灯させない）、
  `ANALYZED` → `max(0, graded - analyzedAnswerCount)`（field 欠落時は 0 件。ただし回答受付時の lazy 初期化により、
  デプロイ後に回答が届いた run は必ず field を持つ）、`GENERATING` / `FAILED` → 0 件。
- 平均スコア率は現行 version の run に紐づく GRADED 回答全体（分析済み含む）の `totalScore / maxScore` 平均。
- 現行 version の GRADED 回答が 0 件、または平均スコア率が計算不能な場合は**消灯**（fail-quiet）。
- DrillAdminPage では、表示中の run が現行 course version の場合のみバッジを表示する（過去 version の run 画面では非表示。
  「過去 run を分析してもバッジが消えない」混乱を避ける）。

## Scope

- **In**:
  - backend: 分析成功時に `DrillRun.analyzed_answer_count` を記録（値は分析開始時に収集した回答集合の件数。
    分析完了処理への最小追記。エージェント側は無変更）
  - backend: `ANALYZED` かつ field 欠落の run への回答受付時の lazy 初期化（回答保存前の GRADED 件数を一度だけ記録）
  - backend: 共有判定関数による computed フィールド `needsAnalysis` を `CourseSummary`（一覧）と
    `DrillAdminResponse`（ドリル管理）の 2 契約に追加
  - frontend: 講座カード（CourseListPage）にアラートバッジ（例: 「低スコア回答が蓄積 — 分析推奨」）。
    **点灯時は既存の「分析できます」チップを置換**し、同一カードに success と warning が並ぶ矛盾を避ける（非点灯時は従来チップ維持）
  - frontend: ドリル管理画面（DrillAdminPage）の「回答を分析する」ボタン付近に同表示（現行 version の run のみ）
  - frontend: 講座一覧の 15 秒間隔ポーリング（既存 API の再取得。重複取得防止・アンマウント時停止を含む）
  - docs/blog.md: DevOps 対応表に「アラート | 誤答閾値超過バッジ」行を追加、「次の周回」を
    「検知は自動化した。次は起動（分析の自動実行）の自動化」に更新
  - シードデータとの整合検証（テストで点灯/消灯を固定。シードデータ自体は無変更）
- **Out**:
  - 通知（メール / Slack 等）
  - 分析の自動実行（起動の自動化）
  - エージェント側（ADK / プロンプト / 分析内容）の変更
  - 講座詳細（CourseEditorPage / `CourseDetailResponse`）へのバッジ追加（表示先は一覧 + DrillAdmin の 2 箇所に絞る）
  - needsAnalysis の Firestore 永続化、WebSocket / SSE / Firestore Listener 等のリアルタイム通信、ドリル管理画面への新規ポーリング追加
  - シードデータの変更、既存 ANALYZED run への一括バックフィル（lazy 初期化で代替）

## Boundary Candidates

- backend の判定基盤（`analyzed_answer_count` の記録 + 共有判定関数）と 2 契約への `needsAnalysis` 追加
- frontend のバッジ表示（一覧カードのチップ置換ロジック / DrillAdmin の表示条件）
- docs/blog.md のナラティブ更新

## Out of Boundary

- 分析パイプラインの判断内容・エージェント挙動（failure-analysis-review-loop の所有。本 spec が触るのは完了時の件数記録のみ）
- シードデータの定義（demo-course-seed の所有。本 spec は読むだけ + 整合テスト追加のみ）
- 通知チャネルの追加

## Upstream / Downstream

- **Upstream**:
  - `demo-course-seed`（点灯/消灯の検証に使うシードデータ、および置換対象の「分析できます」チップ）
  - `hackathon-feedback-loop` / `failure-analysis-review-loop`（分析完了処理 = `analyzed_answer_count` の記録地点、
    回答受付処理 = lazy 初期化の追記地点）
- **Downstream**:
  - 将来の「分析の自動実行（起動の自動化）」（本バッジの判定ルールを再利用する見込み）
  - デモ動画撮影（本 spec のマージが撮影の前提）

## Existing Spec Touchpoints

- **Extends**: なし（新規 spec）
- **Adjacent**:
  - `demo-course-seed` — 講座一覧の「分析できます」チップを所有。本 spec は点灯時のみ同チップを新バッジで置換する
    （非点灯時の表示は不変）。シードデータには触れない
  - `analysis-ui-declutter` — DrillAdmin の Req 1-6 で「実行可否を示す独立チップ」を禁止。新バッジは
    **実行可否ではなく講座の健康アラート**であることを requirements で明確化し、`canAnalyze` 由来の表現と区別する
  - `score-progression-ui` — 同じ `CourseSummary`（schemas.py / types.ts）と CourseListPage.tsx を編集済み。重複回避に注意
  - `failure-analysis-review-loop` — 分析完了処理に `analyzed_answer_count` 記録を追記する（分析の判断内容は不変）

## Constraints

- 判定閾値（N=1、スコア率 70%）は調整可能な定数として実装し、シードデータ無変更で点灯/消灯が成立することをテストで担保する
  （経費精算: ANALYZED + field 欠落・新規回答なし → 未分析 0 件 → 消灯 / ハッカソン: READY 4 件・50% → 点灯）
- requirements では少なくとも次の 3 ケースをテスト対象に含める:
  - field 欠落の既存 ANALYZED run へ新規低スコア回答を 1 件追加 → lazy 初期化により点灯
  - 4 件で分析開始後、分析中に 1 件追加 → 完了後も未分析 1 件として保持（snapshot は分析開始時の収集件数）
  - 初回回答受付（lazy 初期化）と分析完了が並行しても `analyzed_answer_count` の watermark が後退しない
    （古い baseline が分析完了の記録値を上書きしない）
- API レスポンスは既存の camelCase serialization（`to_camel` alias）に従う（`needsAnalysis` / `analyzedAnswerCount`）
- ハッカソン締切 2026-07-12 23:59、優先度は P0 タスク群より後の任意タスク。デモ動画撮影より前にマージすること
- 主要統合ポイント: `backend/app/services/course_service.py` `_summarize`、`backend/app/services/analysis_service.py`
  （`collect_answers` の収集件数を ANALYZED 遷移時に `analyzed_answer_count` として記録）、
  `backend/app/services/answer_service.py` `submit_answer`（lazy 初期化）、
  `backend/app/repositories/repositories.py` `DrillRepository`（`analyzedAnswerCount` 専用の
  条件付き部分更新メソッドの追加。`update_status` と同様の field 単位更新パターン）、`backend/app/schemas.py` `DrillRun` /
  `CourseSummary` / `DrillAdminResponse`、`frontend/src/api/types.ts` `CourseSummary` / `DrillAdmin`、
  `frontend/src/pages/CourseListPage.tsx` `statusChips`（チップ置換）、`DrillAdminPage.tsx` 分析ボタン付近、
  `docs/blog.md` 対応表・「次の周回」
