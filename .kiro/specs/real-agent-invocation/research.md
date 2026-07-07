# Research & Design Decisions — real-agent-invocation

## Summary
- **Feature**: `real-agent-invocation`
- **Discovery Scope**: Extension（既存システムへの統合。light discovery + 外部依存検証）
- **Key Findings**:
  - 呼び出し境界は既に `AgentRuntimeClient`（スキーマ検証・リトライ・ログ）として存在し、`AgentInvoker = Callable[[str, AgentPayload], AgentResponse]` プロトコルの実装を差し替えるだけで実接続に移行できる
  - backend は `google-adk` に依存しておらず、agent パッケージ（`agent/knowledge_drill_agent`）ともリンクされていない。実接続には依存追加とパッケージ参照の確立が必要
  - ADK の `Agent` は `output_schema` 設定済みのため、in-process Runner 実行で最終応答テキストがスキーマ準拠 JSON になることが期待できる（詳細は Research Log 参照）

## Research Log

### 既存の呼び出し境界と検証機構
- **Context**: 実接続の挿入点と、要件4（検証・リトライ・エラー応答）の既存カバレッジを確認するため
- **Sources Consulted**: `backend/app/clients/agent_runtime_client.py`, `backend/app/clients/local_agent_invoker.py`, `backend/app/main.py`
- **Findings**:
  - `AgentRuntimeClient._invoke_typed` が camelCase JSON へのシリアライズ → invoker 呼び出し → `model_validate` 検証 → ValidationError 時に計2回試行 → 失敗で `AgentInvocationError` を実装済み（`agent_runtime_client.py:46-75`）
  - ログはタスク名・レイテンシ・エラー件数のみでペイロード内容を出力しない（要件 4.5 を既に満たす設計）
  - スタブ注入点は `main.py:59` の `AgentRuntimeClient(invoker=LocalAgentInvoker())` の1箇所のみ
  - 4操作のタスク名: `generate_drill` / `grade_answer` / `analyze_failures` / `propose_document_patch`
- **Implications**: 実接続は `AgentInvoker` プロトコルの新実装（AdkAgentInvoker）+ `create_app` での設定駆動の選択、の2点に閉じられる。`AgentRuntimeClient` の検証境界は変更不要（採点の questionId 一致・score 上限は追加が必要）

### 採点応答の整合性検証ギャップ（要件 2.2 / 2.3）
- **Context**: レビュー指摘。実LLM応答は questionId の取り違え・score 超過があり得る
- **Sources Consulted**: `backend/app/schemas.py:140-205`, `backend/app/services/answer_service.py`
- **Findings**:
  - `GradingResult.score` は `ge=0, le=4` の固定範囲のみで、`question.max_score` との比較はない
  - `GradingResult.question_id` とリクエストの `question.id` の一致検証はどこにもない
  - 採点は設問ごとに1回ずつ `grade_answer` を呼ぶループ（`answer_service.py:61-67`）
- **Implications**: `AgentRuntimeClient.grade_answer` にリクエスト文脈を使った事後検証（questionId 一致・score <= question.max_score）を追加し、不一致はスキーマ不適合と同様に再試行→エラーのパスに乗せる

### backend と agent パッケージの依存関係
- **Context**: in-process 実行には backend から ADK エージェント定義を import できる必要がある
- **Sources Consulted**: `backend/pyproject.toml`, `agent/pyproject.toml`, `backend/tests/test_runtime_dependencies.py`
- **Findings**:
  - backend 依存: fastapi / google-cloud-aiplatform[agent-engines] / google-cloud-firestore / httpx / pydantic-settings / uvicorn。`google-adk` なし
  - agent 依存: `google-adk>=1.0.0` のみ。両パッケージは独立した uv プロジェクトでリンクなし
  - `test_runtime_dependencies.py` が backend 依存リストを assert しており、依存追加時に更新が必要
- **Implications**: backend に `google-adk` と agent パッケージへのパス依存（uv sources）を追加する。エージェント定義・プロンプト・スキーマは agent パッケージ側の所有を維持し、backend は import のみ行う

### ADK in-process 実行 API（外部調査・確定）
- **Context**: `adk` CLI を使わず FastAPI プロセス内から Agent を決定的に1回実行する方法の確認
- **Sources Consulted**: deepwiki (google/adk-python) Q&A、PyPI google-adk、adk-python CHANGELOG / releases
- **Findings**:
  - 標準パターン: `google.adk.runners.Runner`（エージェントごとに1つ、起動時に構築して再利用）+ `google.adk.sessions.InMemorySessionService`（共有可）。呼び出しごとに `await session_service.create_session(...)` → `runner.run_async(user_id=..., session_id=..., new_message=types.Content(...))` をイテレートし、`event.is_final_response()` の `content.parts[0].text` を取得
  - `output_schema` 設定時は最終応答テキストがスキーマ準拠 JSON（controlled generation）。防御的な再検証は推奨（本設計では backend の Pydantic 境界が担う）
  - `input_schema` は Runner 直接呼び出しでは**強制されない**（AgentTool 経由でのみ検証）。ペイロードはスキーマ準拠の JSON 文字列としてユーザーメッセージに渡す規約とする
  - 認証: AI Studio モード（`GOOGLE_API_KEY`）または Vertex AI モード（`GOOGLE_GENAI_USE_VERTEXAI=TRUE` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION`）。google-genai Client 構築時に環境変数から検出される
  - 同期 `Runner.run()` も存在（内部でスレッド+イベントループを生成）が、実行中のイベントループスレッドから呼んではならない
  - `RunConfig` に確実なタイムアウトフィールドはバージョン差があるため、呼び出し全体を `asyncio.wait_for` で包むのが堅牢
  - バージョン: agent/uv.lock は **google-adk 2.3.0** を解決済み。`run_async(user_id=, session_id=, new_message=)` は 1.0 以降安定。2.3.0 でデフォルトモデルが変わったため `gemini-2.5-flash` の明示指定（既存の agent config が対応済み）が重要
  - 注意: ADK のエージェントは単一親制約があり、リーフエージェントは `root_agent.sub_agents` に登録済み。個別 Runner での実行と衝突する場合は agent パッケージにスタンドアロン生成のファクトリを追加する
- **Implications**: root_agent（LLM 判断のサブエージェント転送）は使わず、タスク名→リーフエージェントの決定的マッピングで 4 Runner を構築する。JSON パース失敗・スキーマ逸脱は `AgentRuntimeClient` の既存検証・再試行パスで吸収する

### FastAPI ルートの同期・非同期構造とイベントループブロッキング
- **Context**: 実LLM呼び出しは数秒〜数十秒かかる。要件 4.2「他の操作の処理は継続する」の成立条件を確認
- **Sources Consulted**: `backend/app/routes/*.py`, `backend/app/errors.py`
- **Findings**:
  - 全ルートが `async def` で同期サービスを直接呼んでいる。スタブは即時応答のため顕在化していないが、実接続では 1 件のエージェント呼び出し中にイベントループ全体（他 API・ヘルスチェック含む）が停止する
  - `errors.py` は AppError / RequestValidationError / 汎用 Exception のハンドラを登録済み。`AgentInvocationError` 専用ハンドラはなく、現状は汎用 500 に落ちる
- **Implications**: エージェント操作に到達する5ルート関数（courses.py の generate_drill / analyze_course_drill、drills.py の analyze_drill、learn.py の submit_answer / submit_answer_legacy）を `def` に変更し FastAPI のスレッドプールで実行する（API 契約は不変）。legacy は `await submit_answer(...)` で委譲しているため同時変更が必須。`AgentInvocationError` → 502 の専用ハンドラを追加し、要件 4.2/4.3 の「サーバーエラー応答 + 稼働継続」を明示的に満たす

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| A: ADK Runner in-process | backend プロセス内で Runner を生成し 4 リーフエージェントを直接実行 | 追加インフラ不要・レイテンシ最小・締切内で完了可能・ローカルでも動く | backend が google-adk に依存。プロセス内で LLM 待ちが発生 | **採用**。7/10 締切に対する最小構成 |
| B: Agent Engine（Vertex AI）デプロイ | agent を Agent Engine にデプロイし backend からリモート呼び出し | スケーラビリティ・関心分離 | デプロイパイプライン整備が必要で締切リスク大。ローカル開発に常時クラウド接続が必要 | 後続（Cloud Run 化以降）の発展オプションとして温存 |
| C: root_agent 経由の転送 | root_agent に全リクエストを渡し sub_agents へ LLM 転送させる | エージェント構成に忠実 | 転送判断が非決定的でタスク種別が既知の本ケースでは無駄なホップ・失敗モード追加 | 不採用。タスク名→リーフエージェントの決定的マッピングで十分 |

## Design Decisions

### Decision: AdkAgentInvoker を既存 AgentInvoker プロトコルの実装として追加する
- **Context**: 要件1〜3の実接続を、既存 API 契約（要件6）を壊さず実現する
- **Alternatives Considered**:
  1. サービス層から直接 ADK を呼ぶ — 検証境界とログが分散し要件4の保証が崩れる
  2. AgentRuntimeClient を書き換えて ADK 専用にする — スタブモード（要件5.3）が消える
- **Selected Approach**: `AgentInvoker` プロトコル（`Callable[[str, AgentPayload], AgentResponse]`）の新実装 `AdkAgentInvoker` を追加し、`create_app` が設定でスタブ実装と切り替える
- **Rationale**: 差し替え点が1箇所（main.py の注入）に閉じ、既存テスト・検証・ログがそのまま生きる
- **Trade-offs**: invoker が同期プロトコルのため、ADK の async 実行をブリッジする必要がある
- **Follow-up**: FastAPI のイベントループ内から同期的にブロックしない実行方式（スレッド + 独立ループ等）の実装確認

### Decision: 実行モードは backend Settings の明示フラグで切り替える
- **Context**: 要件5（実接続／スタブの運用設定切り替え、認証欠落の起動時報告）
- **Alternatives Considered**:
  1. 認証情報の有無で自動判定 — 設定ミス時に意図せずスタブで動き、ハッカソン審査中に「実AIでない」状態になり得る
  2. ビルド時分岐 — CI とローカルの両立が煩雑
- **Selected Approach**: `KNOWLEDGE_DRILLS_AGENT_MODE=adk|local`（既定 `local`）を Settings に追加。`adk` 選択時は起動時に認証設定を検証し、欠落なら明確なエラーで fail fast
- **Rationale**: 明示的なモードは誤構成を起動時に検出でき、要件5.4 に直接対応する
- **Trade-offs**: デプロイ設定に1変数追加
- **Follow-up**: Cloud Run デプロイスペックでのデフォルト値の扱い

### Decision: 採点応答の文脈整合性検証を AgentRuntimeClient に置く
- **Context**: 要件 2.2 / 2.3（score 範囲・questionId 一致）。Pydantic スキーマ単体ではリクエスト文脈と突き合わせできない
- **Selected Approach**: `grade_answer` にタスク固有の事後検証（`response.question_id == request.question.id` かつ `response.score <= request.question.max_score`）を追加し、違反は ValidationError と同じ再試行→`AgentInvocationError` パスで処理
- **Rationale**: 検証境界を1箇所（AgentRuntimeClient）に保つ方針（要件・設計原則）と一致。invoker 実装（スタブ/ADK）に依存しない保証になる
- **Trade-offs**: `_invoke_typed` にフックが1つ増える
- **Follow-up**: スタブモードの既存テストが新検証を通ることの確認

### Decision: 同期 invoker プロトコルを維持し、asyncio.run + wait_for でブリッジする
- **Context**: `AgentInvoker` は同期 Callable。ADK の実行は async が基本。タイムアウト（要件4.4）も必要
- **Alternatives Considered**:
  1. ADK の同期 `Runner.run()` を使う — タイムアウト制御がバージョン依存（RunConfig の互換性が不確実）
  2. invoker プロトコルを async 化 — サービス層・既存テスト全体に波及し締切リスク
- **Selected Approach**: `AdkAgentInvoker.__call__`（同期）内で `asyncio.run(asyncio.wait_for(self._invoke_async(...), timeout))` を実行。呼び出し元はスレッドプール上の同期ルートなので新規ループ生成は安全
- **Rationale**: プロトコル不変で差し替え可能性を維持しつつ、バージョン非依存の確実なタイムアウトを得る
- **Trade-offs**: 呼び出しごとのループ生成コスト（LLM レイテンシに対し無視できる）
- **Follow-up**: `TimeoutError` / genai 例外 → `AgentInvocationError` への変換とログ（ペイロード非出力）

### Decision: エージェント操作に到達するルートを def（スレッドプール実行）に変更する
- **Context**: 全ルートが `async def` で同期サービスを呼ぶため、実LLM呼び出し中にイベントループが停止し要件 4.2 に反する
- **Alternatives Considered**:
  1. `run_in_threadpool` でサービス呼び出しを包む — ルートごとに散発的な async 化が混じり読みにくい
  2. サービス層全体の async 化 — 波及が大きく締切リスク
- **Selected Approach**: エージェント操作に到達する5ルート関数（`generate_drill` / `analyze_course_drill` / `analyze_drill` / `submit_answer` / `submit_answer_legacy`）を `async def` → `def` に変更（FastAPI が自動でスレッドプール実行）。`submit_answer_legacy` は `await submit_answer(...)` で委譲しているため両方同時に変更し `await` を外す。API 契約は不変
- **Rationale**: 最小差分でイベントループ停止を回避。エージェントを呼ばないルートは現状維持
- **Trade-offs**: スレッドプールサイズ（デフォルト40）が同時エージェント呼び出しの上限になる（MVP では十分）

## Risks & Mitigations
- リーフエージェントの単一親制約（root_agent.sub_agents 登録済み）と個別 Runner 実行の衝突 — 実装冒頭に検証し、衝突する場合は agent パッケージにスタンドアロン生成ファクトリを追加（プロンプト・スキーマの所有は agent パッケージのまま）
- LLM 応答の不安定さ（不正 JSON・スキーマ逸脱）— 既存の再試行 + Pydantic 境界検証で吸収。プロンプトは agent パッケージ側で調整
- 実接続時のレイテンシ増（数秒〜数十秒）— タイムアウトを設定可能にし超過時はエラー応答（要件4.4）。UI 側は既存の同期フローを維持（本スペックでは変更しない）
- `google-adk` と `google-cloud-aiplatform` の依存衝突 — uv lock で解決可否を実装冒頭に確認
- 契約テストの独立性（要件6.2）— ADK 呼び出し部はユニットテストでスタブ化し、実 API を叩くテストは作らない

## References
- [google/adk-python](https://github.com/google/adk-python) — Runner / Session API（deepwiki 調査）
- [ADK Docs: Runtime](https://google.github.io/adk-docs/) — in-process 実行・認証環境変数
- `docs/hackathon-strategy.md` — 本スペックの位置づけ（Phase 0 前提タスク）
