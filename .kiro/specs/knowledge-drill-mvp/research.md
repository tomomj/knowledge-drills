# Research & Design Decisions

## Summary
- **Feature**: `knowledge-drill-mvp`
- **Discovery Scope**: New Feature / Complex Integration
- **Key Findings**:
  - 既存実装はなく、`docs/knowledge-drill-agent-engine-spec.md` が唯一の技術仕様である。設計はグリーンフィールド前提で、FastAPI backend、Vite frontend、Agent Runtime、Firestore の責務境界を明確化する必要がある。
  - Gemini Enterprise Agent Platform の Agent Runtime は ADK agent をホストする実行基盤として扱い、Python 側の SDK には `google-cloud-aiplatform[agent_engines,adk]>=1.112.0` が quickstart で示されている。製品名は Agent Platform / Agent Runtime、Python API namespace は `agent_engines` として整理する。
  - Patch apply / stale 判定、回答採点失敗、Agent 出力検証失敗は、UI 表示だけでなく永続状態として表現する必要がある。Firestore transaction と Pydantic schema 検証を設計上の境界に置く。
  - shareToken は高エントロピーだけに頼らず、`share_tokens/{token}` 予約 document の create-only 書き込みで構造的に一意性を担保する。

## Research Log

### ローカル仕様とコードベース状況
- **Context**: `$kiro-spec-design knowledge-drill-mvp -y` により、requirements 承認済みとして設計生成を進める。
- **Sources Consulted**: `.kiro/specs/knowledge-drill-mvp/requirements.md`, `docs/knowledge-drill-agent-engine-spec.md`, repository file listing。
- **Findings**:
  - 実装ファイルはまだ存在せず、`AGENTS.md`、仕様書、Kiro spec のみが存在する。
  - `.kiro/steering/` は存在しないため、プロジェクト横断の命名・構成・セキュリティ方針は未定義である。
  - requirements は 10 領域、48 個の受け入れ条件を持ち、Course、Drill、Answer、Analysis、Patch、Security、Error visibility を横断する。
- **Implications**:
  - 設計では具体的なファイル構造を新規に定義し、タスク生成が迷わない粒度で backend / frontend / agent / infra を分ける。
  - steering 不在の制約を明記し、後続で steering が追加された場合は設計再検証を行う。

### Agent Runtime / ADK 連携
- **Context**: DrillGeneratorAgent、GradingAgent、FailureAnalysisAgent、DocumentPatchAgent を Agent Runtime 上で実行する。
- **Sources Consulted**:
  - https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime
  - https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk
- **Findings**:
  - Agent Runtime は AI agent のデプロイ、管理、スケーリングを担う実行基盤として扱う。
  - ADK quickstart は `google-cloud-aiplatform[agent_engines,adk]>=1.112.0` と `google-adk` を使う Python workflow を示している。
  - 仕様書の製品名は Agent Platform / Agent Runtime に統一しつつ、Python 実装では `agent_engines` namespace が出ることを許容する。
- **Implications**:
  - backend は Agent の内部状態や Firestore 書き込みを Agent に委譲しない。Agent 入出力を Pydantic schema で検証し、失敗時は backend 側の状態に反映する。
  - Agent は domain schemas と prompts を shared contract として実装し、backend とは JSON contract で接続する。

### FastAPI と Pydantic 境界
- **Context**: API と Agent 出力検証を型安全に実装する。
- **Sources Consulted**:
  - https://fastapi.tiangolo.com/tutorial/response-model/
- **Findings**:
  - FastAPI は path operation の response model により出力データの validation、serialization、documentation を行える。
  - Pydantic model を API request / response と Agent output schema に使うと、受講者向け API から rubric / idealAnswer を除外する境界を明示できる。
- **Implications**:
  - backend は `schemas.py` を API / domain / agent output で分け、Learner response model と Admin response model を別定義にする。
  - 曖昧な汎用型は使わず、Literal union と Optional field を明示する。

### Firestore 状態管理と一貫性
- **Context**: Patch apply / stale 判定、answer failed、drill failed を永続化する。
- **Sources Consulted**:
  - https://firebase.google.com/docs/firestore/manage-data/transactions
- **Findings**:
  - Firestore transactions は読み取り後に書き込みを行い、競合時に再試行される。transaction 内の writes は部分適用されない。
  - Patch apply は course markdown と patch status の同時更新が必要で、baseMarkdown 比較を transaction 境界に入れるべきである。
- **Implications**:
  - `PatchService.apply_patch` と `reject_patch` は transaction を使い、`patch.status == proposed` と `patch.baseMarkdown == course.markdown` を同じ整合性境界で評価する。
  - `GET /api/patches/:patchId` でも proposed patch の stale 判定を行い、UI が Apply 不可状態を即時表示できるようにする。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Layered FastAPI + React | API handlers、services、repositories、UI を分ける標準構成 | MVP で実装しやすく、タスク分割が明確 | domain が薄い場合に service が肥大化しやすい | 採用。今回の規模に合う |
| Hexagonal ports and adapters | domain core を ports で外部依存から隔離 | Agent Runtime / Firestore を交換しやすい | MVP には抽象層が重い | Agent client と repository は薄い adapter として局所採用 |
| Event driven / async job | drill generation や analysis を job 化 | 長時間 Agent 呼び出しに強い | MVP の同期要件より複雑 | 30 秒超過が実測されたら再検討 |
| Monolithic frontend-only prototype | browser から直接処理する | 初期画面を早く作れる | Secret、rubric、idealAnswer、Firestore 書き込み境界が崩れる | 不採用 |

## Design Decisions

### Decision: FastAPI を信頼境界にする
- **Context**: shareToken 検証、rubric 非公開、diff 生成、Patch apply/reject は Agent に任せないと仕様で定義されている。
- **Alternatives Considered**:
  1. Agent が Firestore も更新する。
  2. frontend が Agent Runtime を直接呼ぶ。
  3. FastAPI が API validation、Agent 呼び出し、Firestore 更新を統制する。
- **Selected Approach**: FastAPI service layer を唯一のアプリケーション信頼境界とする。
- **Rationale**: Secret と管理データを frontend / Agent から分離でき、受講者向け response model を制御できる。
- **Trade-offs**: backend service の責務は増えるが、MVP のセキュリティ境界が明確になる。
- **Follow-up**: 実装時に service account 権限を最小化する。

### Decision: Agent 出力は Pydantic schema で検証し、1 回だけ retry する
- **Context**: Agent 出力は不完全または schema 違反の可能性がある。
- **Alternatives Considered**:
  1. JSON をそのまま保存する。
  2. schema 違反時に無制限 retry する。
  3. schema validation 後、1 回 retry し、それでも失敗なら failed 状態にする。
- **Selected Approach**: 1 回 retry + failed status。
- **Rationale**: ユーザーに再試行可能な状態を返しつつ、無限待機や不完全表示を避ける。
- **Trade-offs**: 一時的な Agent 不調でユーザー操作が必要になる場合がある。
- **Follow-up**: Agent latency と validation error reason を logging する。

### Decision: Patch apply/reject は transaction と状態遷移で守る
- **Context**: Patch 生成後に course markdown が変わると stale になる。
- **Alternatives Considered**:
  1. UI 側だけで stale を判定する。
  2. Apply 時だけ backend で stale 判定する。
  3. Patch 取得時と Apply/Reject 時の両方で stale を判定する。
- **Selected Approach**: Patch 取得時に表示用 stale 判定、Apply/Reject 時に transaction で最終判定。
- **Rationale**: レビュー画面の誤操作を減らし、競合時も course 更新を防げる。
- **Trade-offs**: Patch 取得が read-only ではなく状態更新を伴う。
- **Follow-up**: GET の副作用が問題になる場合は `refresh-status` endpoint へ分離する。

### Decision: current scope では同期 Agent 呼び出しを採用する
- **Context**: 仕様書は 30 秒を超える可能性がある場合のみ background job 化を後続フェーズへ送る。
- **Alternatives Considered**:
  1. 最初から Cloud Tasks を導入する。
  2. すべて同期 API で実行する。
  3. drill / analysis だけ非同期にする。
- **Selected Approach**: MVP では同期 API を基本にし、状態は generating / analyzing / failed で表現する。
- **Rationale**: MVP の検証仮説に対して最小構成で十分であり、複雑な job orchestration を避けられる。
- **Trade-offs**: Agent latency が大きい場合に UX が悪化する。
- **Follow-up**: 30 秒超過や timeout が多発した時点で background job spec を追加する。

### Decision: Analysis 状態遷移を DrillRun に集約する
- **Context**: 分析中表示、失敗表示、最新 Patch 表示は requirements 1.5, 10.2, 10.3, 10.5 に関わる。
- **Alternatives Considered**:
  1. Patch document だけで分析状態を表す。
  2. UI local state だけで分析中を表す。
  3. DrillRun status を `analyzing -> analyzed | failed` として永続化する。
- **Selected Approach**: AnalysisService が drill_run.status を開始時 `analyzing`、成功時 `analyzed`、失敗時 `failed` に更新する。成功時は course.latestPatchId も更新する。
- **Rationale**: Course detail、Drill Admin、Patch Review が同じ永続状態を参照でき、retry 表示も実装者依存にならない。
- **Trade-offs**: drill generation failure と analysis failure が同じ `failed` status を使うため、errorMessage と operation context の logging が重要になる。
- **Follow-up**: 実装時に failed の原因区分が必要なら `errorCode` を追加する。

### Decision: shareToken 一意性を予約 document で保証する
- **Context**: token collision は低確率でも別 drill への誤共有につながる。
- **Alternatives Considered**:
  1. 高エントロピー token と query による collision check のみ。
  2. drill_runs の shareToken field に unique index を期待する。
  3. `share_tokens/{token}` document id を create-only で予約する。
- **Selected Approach**: token を document id とする `share_tokens/{token}` を transaction 内で create し、同じ transaction で drill_run を作成する。
- **Rationale**: Firestore に unique constraint がなくても document id の create-only semantics で構造的に一意性を担保できる。
- **Trade-offs**: collection が 1 つ増える。
- **Follow-up**: token collision をテストで強制できるよう、token generator を dependency injection 可能にする。

## Risks & Mitigations
- Agent Runtime の API や SDK が更新される — 公式 quickstart の SDK version と deployment flow を実装時に再確認する。
- Agent 出力が schema を満たさない — Pydantic validation、1 回 retry、failed status、validation error logging で封じる。
- Patch apply の競合で course が意図せず更新される — Firestore transaction と `baseMarkdown` 比較で防ぐ。
- 分析状態が UI と永続化でずれる — AnalysisService が drill_run.status と course.latestPatchId を単一の責務として更新する。
- shareToken collision — `share_tokens/{token}` 予約 document により構造的に一意性を担保する。
- 受講者向け API に rubric / idealAnswer が漏れる — Learner 専用 response model と contract test を必須にする。
- steering が未整備 — design review 時に `.kiro/steering/` 追加有無を revalidation trigger とする。

## References
- [Gemini Enterprise Agent Platform / Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime) — Agent Runtime の位置付け。
- [Agent Runtime quickstart with ADK](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk) — ADK agent の deployment と Python SDK。
- [FastAPI response model](https://fastapi.tiangolo.com/tutorial/response-model/) — API response validation と serialization。
- [Cloud Firestore transactions](https://firebase.google.com/docs/firestore/manage-data/transactions) — Patch apply / stale 判定の一貫性境界。
