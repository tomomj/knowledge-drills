# Research & Design Decisions

## Summary
- **Feature**: `hackathon-feedback-loop`
- **Discovery Scope**: Extension（既存システムへの統合中心）
- **Key Findings**:
  - 対象 6 機能（drillFocus、根拠検証、scoreSummary、タイムライン、多視点分析、metrics）はすべて未実装であり greenfield 追加である
  - backend の API model は `ApiModel`（camelCase alias、frozen）で統一されており、更新は `model_copy(update={...})` 経由。DrillRun / DocumentPatch への field 追加はこの規約に従う
  - agent 呼び出しは `AgentRuntimeClient` -> `AgentInvoker`（`LocalAgentInvoker` / `AdkAgentInvoker`）の抽象があり、`AdkAgentInvoker` は task 名ごとに factory（`_TASK_AGENT_FACTORIES`）から leaf Agent を作って Runner 実行する。多視点化は factory の返す Agent を composite にするだけで backend 契約を維持できる
  - frontend には polling パターンが存在しない。DrillAdminPage に本機能で初めて interval polling を導入する
  - 詳細実装設計は `docs/hackathon-feedback-loop-feature-design.md` に既に存在し、本 spec はそれを要件・設計・タスクの形式に正規化する

## Research Log

### 既存 backend 統合ポイント
- **Context**: 6 機能の変更対象ファイルと既存規約の確認
- **Sources Consulted**: backend/app/schemas.py、services/、routes/、config.py、repositories/repositories.py
- **Findings**:
  - `Course`(schemas.py:74) に drill_focus を追加。`CourseCreateRequest`/`CourseUpdateRequest` は {title, markdown} のみ
  - `DrillQuestion.source_evidence` は `min_length=1` 済み。excerpt の教材実在チェックは `DrillService._validate_questions`(drill_service.py:224) に追加（現在は設問数・rubric 合計・evidence 非空のみ）
  - `AnalysisService.run_analysis` が start_analysis -> analyze_failures -> propose_document_patch -> patch 保存を直列実行。timeline の段階保存はこの各境界に挿入する
  - 採点集計の元データは `AnswerRepository` の graded answers（AnswerService が total_score/max_score を保存済み）
  - metrics endpoint は存在しない。routes/courses.py に `GET /{course_id}/metrics` を追加（router レベルで `require_current_user` 適用済み）
  - `Settings` は `env_prefix="KNOWLEDGE_DRILLS_"`、`Literal` で mode 系 flag を定義（`agent_mode: "local"|"adk"` の前例あり）
- **Implications**: 変更はすべて既存パターンの延長で実装でき、新しい層・新しい repository は不要

### ADK composite agent（SequentialAgent / ParallelAgent）
- **Context**: failure_analysis_agent の多視点化（Requirement 5）の実装方式
- **Sources Consulted**: agent/knowledge_drill_agent/agent.py、backend/app/clients/adk_agent_invoker.py、ADK 既知仕様
- **Findings**:
  - `SequentialAgent` / `ParallelAgent` は `google.adk.agents` の composite で、`instruction` / `input_schema` / `output_schema` を持たない。leaf `LlmAgent` の `output_key` が session state に最終応答を保存し、後続 agent の instruction 内 `{state_key}` placeholder で参照できる
  - SequentialAgent の最終応答は最後の sub_agent の応答。よって synthesis agent に `output_schema=FailureAnalysisOutput` を付ければ、Runner から見た応答契約は現行 leaf agent と同一になる
  - Agent インスタンスは単一 parent 制約があるため、composed 版も factory 関数で毎回新規生成する現行方式（`create_failure_analysis_agent()`）を踏襲する
  - evals は `evals/failure_analysis/agent.py` の `root_agent = create_failure_analysis_agent()` を discovery する。composite を root_agent にしても最終応答ベースの rubric eval（`rubric_based_final_response_quality_v1`）はそのまま機能する見込み
  - `backend/tests/test_adk_leaf_agents.py` 等が leaf 前提の assert を持つ可能性があり、テスト更新が必要
- **Implications**: 多視点化は agent パッケージ内に閉じ、backend は `_TASK_AGENT_FACTORIES` の参照先 factory が composite を返すことを許容するだけでよい

### frontend 統合ポイント
- **Context**: scoreSummary / タイムライン polling / metrics 比較カードの配置
- **Sources Consulted**: frontend/src/api/client.ts、api/types.ts、pages/、components/common/
- **Findings**:
  - API 型は api/types.ts、client は api/client.ts の `api` オブジェクトに集約
  - polling パターンは未存在。既存ページは `useEffect` + `active` cleanup flag の単発 load
  - 共有 UI は components/common/（AppShell、DiffViewer、StatusBanner 等）。AnalysisTimeline も同階層に置く
  - テストは Vitest + Testing Library、ソース隣接の `*.test.tsx`
- **Implications**: polling は DrillAdminPage 内の interval + cleanup で実装し、SSE/WebSocket は導入しない（設計 md 5.4 節と一致）

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 同期 POST + GET polling | analyze POST を維持し、frontend が DrillAdmin GET を interval 取得 | インフラ追加なし、既存 API 形状維持 | 完了検知が最大 interval 分遅れる | 採用。設計 md 5.4 節 |
| SSE / WebSocket | 分析進捗を push 配信 | リアルタイム性 | Cloud Run 設定・接続管理の追加工数、締切リスク | 不採用（Out of scope） |
| 単一 improvement_agent 統合 | 分析と patch を 1 agent に統合 | agent 呼び出し 1 回 | 判断ログの構造化が難しく、撤退経路がない | 不採用（設計 md 6.5 は見送り済み） |
| composed failure analysis | Sequential(Parallel(3 lenses) -> synthesis) | 契約維持・視点別根拠・env 撤退可能 | agent 呼び出し回数 4 倍（コスト/レイテンシ） | 採用。Requirement 5 |

## Design Decisions

### Decision: 根拠検証は backend 境界で行う
- **Context**: Requirement 2。agent 出力のハルシネーションを構造的に遮断する
- **Alternatives Considered**:
  1. prompt のみで抑制 — 検証保証がない
  2. agent 側 validator — LocalAgentInvoker や将来の invoker に効かない
- **Selected Approach**: `DrillService._validate_questions(questions, course_markdown)` に excerpt の完全一致包含チェックを追加。失敗時は既存の `drill generation failed` フローに載せる
- **Rationale**: invoker 実装に依存しない唯一の境界であり、既存 status 遷移・リトライ（AgentRuntimeClient の 2 回リトライ）をそのまま使える
- **Trade-offs**: 正当な言い換え excerpt も reject する（完全一致要件）。prompt 側で「原文をそのまま引用する」制約を強化して補う
- **Follow-up**: 実 Gemini eval で excerpt 完全一致率を確認する

### Decision: タイムラインは AnalysisService が組み立て、agent には作らせない
- **Context**: Requirement 4。判断ログは Chain-of-thought ではなく監査ログとして扱う
- **Alternatives Considered**:
  1. agent 出力に timeline を含めさせる — 内部推論の漏出リスク、schema 契約の肥大化
  2. backend が観測値から組み立てる — agent 出力からは要約のみ利用
- **Selected Approach**: `AnalysisService` が固定 5 step（collect_answers / detect_failure_patterns / match_course_evidence / decide_patch_strategy / create_patch）を段階保存し、summary/evidence には集計値と agent 出力の構造化 field（failure_signals、target_sections、perspectives）だけを使う
- **Rationale**: 表示内容を観測値・根拠・判断結果に限定でき（Requirement 4.6）、agent 契約変更を最小化できる
- **Trade-offs**: step 粒度は backend の処理順に固定される
- **Follow-up**: 分析失敗時に running step が failed になることをテストで保証

### Decision: 多視点分析は agent パッケージ内 composite + env 切り替え
- **Context**: Requirement 5。多視点化しつつ締切直前でも撤退可能にする
- **Alternatives Considered**:
  1. backend で 3 回 analyze_failures を呼び分ける — API 呼び出し・タイムアウト管理が backend に漏れる
  2. agent 内 composite（採用） — Runner から見た契約が不変
- **Selected Approach**: `create_failure_analysis_agent()` が agent 設定 `KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE`（`single` | `composed`、default `composed`）に応じて leaf または `SequentialAgent(ParallelAgent(3 lenses), synthesis)` を返す。`FailureAnalysisOutput` に optional `perspectives` を追加（契約は後方互換）。default を composed にするのは、Requirement 5.1 が多視点分析を必須としており default deploy で要件を満たす必要があるため（レビュー指摘による変更）。`single` は撤退用の明示指定
- **Rationale**: backend・evals・root_agent の参照先が factory のため、切り替えが 1 点に集約される。撤退は env 1 つ
- **Trade-offs**: LLM 呼び出しが 1 -> 4 回（コスト・レイテンシ増）。分析は低頻度操作のため許容
- **Follow-up**: adk eval が composite root_agent を discovery できることを CI で確認。`test_adk_leaf_agents.py` の leaf 前提 assert を更新

### Decision: scoreSummary / metrics は読み取り時集計（保存しない）
- **Context**: Requirement 3・6。集計値の保存は回答追加ごとの整合性管理を生む
- **Alternatives Considered**:
  1. 集計値を DrillRun に保存 — 書き込み経路が増え、answer 提出との整合性が必要
  2. 読み取り時に AnswerRepository から集計（採用）
- **Selected Approach**: `DrillService` が admin 取得時に graded answers から `DrillScoreSummary` を構築。`CourseService.get_course_metrics` が drill run ごとに同じ集計を行う
- **Rationale**: デモ規模（回答数十件）では読み取り集計で十分。整合性バグの入り口を作らない
- **Trade-offs**: 回答数が大きい講座では admin 取得が重くなる（本ハッカソン範囲では非問題）
- **Follow-up**: 回答 0 件時の null 扱いをテストで固定

### Decision: 分析ライフサイクルで share URL を無効化しない
- **Context**: 既存 `get_learner_drill` は `status != READY` を 404 にするため、分析開始（analyzing）・完了（analyzed）・失敗（failed）のいずれでも share URL が壊れる。「受講者体験は変更しない」と衝突する（設計レビュー指摘・高）
- **Alternatives Considered**:
  1. `analysis_status` を DrillRun の別 field に分離 — 最もクリーンだが、既存の status 遷移・frontend 表示・テストへの波及が大きく締切リスク
  2. learner 配布可能 status の allowlist 拡張 + 分析失敗時は ready へ戻す（採用）
- **Selected Approach**: `get_learner_drill` は {ready, analyzing, analyzed} を配布可能とする。分析失敗時は実行中 step を failed にし error_message を記録したうえで `status=ready` へ戻す（失敗の監査証跡は timeline に残る。再分析も ready から自然に可能）。generating / 生成失敗の failed は従来どおり 404
- **Rationale**: 単一 status field を維持したまま最小 diff で受講者体験を保護できる。ドリル自体は分析の成否に関わらず有効であり、「分析失敗 = 配布不可」に意味的必然性がない
- **Trade-offs**: 分析失敗が status からは読めなくなる（timeline と error_message が担う）
- **Follow-up**: 既存の「分析失敗で FAILED」を前提にしたテストの更新。integration テストで analyzed 後の share URL 取得を保証

## Risks & Mitigations
- excerpt 完全一致検証で drill generation の failed 率が上がる — prompt に「教材原文をそのまま引用」制約を追加し、実 eval で確認。失敗時は既存リトライで吸収
- composite agent が adk eval / 既存テストの leaf 前提を壊す — default を `single` にして段階投入。eval・テスト更新を同タスクに含める
- polling とPOST 完走の競合（POST 完了後も polling が走る） — cleanup と遷移条件を DrillAdminPage のテストで固定
- 締切（2026-07-10）までに全量が入らない — タスクは 1〜3（P0）、6（metrics）、4〜5（多視点）の順に独立して完了可能な構成にする

## References
- `docs/hackathon-feedback-loop-feature-design.md` — 本 spec の実装設計ソース（v0.2）
- `.kiro/specs/google-login-owner-scope/` — 認証・owner scope の隣接 spec
- `.github/workflows/agent-eval.yml` — rubric ベース LLM judge の CI ゲート
- Google ADK: SequentialAgent / ParallelAgent / output_key / state placeholder の公式仕様
