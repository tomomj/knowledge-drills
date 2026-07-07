---
name: backend-fastapi
description: Knowledge Drills の FastAPI backend のアーキテクチャと実装規約。Codex が backend/ 配下で FastAPI、Pydantic v2、uv、pytest、ruff、mypy、httpx、pydantic-settings、Google Firestore、Google ADK、AgentRuntimeClient、AdkAgentInvoker、local/adk 実行モードを使う API 実装、リファクタリング、レビュー、テスト追加、依存関係整理を行うときに使う。
---

# Backend FastAPI MVP 規約

FastAPI backend の作成、編集、レビューではこの規約を適用する。MVP では過剰な Clean Architecture や細かい directory 分割より、薄い route、明確な service、必要最小限の client、型安全な schema を優先する。

## 標準構成

新規 backend は原則として次の構成から始める。

```text
backend/
├── pyproject.toml
├── app/
│   ├── main.py
│   ├── config.py
│   ├── schemas.py
│   ├── errors.py
│   ├── routes/
│   ├── services/
│   ├── repositories/
│   └── clients/
└── tests/
    ├── conftest.py
    ├── test_health.py
    └── test_drills.py
```

- `routes/` は FastAPI router を置く。route は薄く保つ。
- `services/` は業務ロジックを置く。MVP でも route にロジックを詰め込まない。
- `clients/` は Agent / ADK など接続先ごとの client を置く。
- `repositories/` は Firestore と in-memory repository 境界を置く。
- `schemas.py` は Pydantic model を置く。MVP では単一ファイルで始める。
- `config.py` は環境変数と application settings を扱う。
- `errors.py` は application exception と FastAPI exception handler を扱う。

## 最初は作らないもの

MVP では次を標準では作らない。

- `integrations/`
- `utils/`
- `schemas/` directory
- `domain/` directory
- `dependency-injector` などの DI framework
- 本格的な Clean Architecture の adapter/interface 層

必要になったら分割する。最初から置き場だけ作らない。

## 依存方向

依存方向は次を守る。

```text
config / schemas
  -> clients
  -> services
  -> routes
  -> main
```

- `routes` から DB SDK や外部 API SDK を直接呼ばない。
- `services` は route-specific な `Request` や `Response` に依存しない。
- `clients` は外部接続の詳細を閉じ込める。
- `schemas.py` は基本的に全層から参照してよいが、循環 import を作らない。

## Runtime dependencies

標準 runtime dependencies は次にする。

```toml
dependencies = [
  "fastapi",
  "uvicorn[standard]",
  "pydantic-settings",
  "httpx",
]
```

- `fastapi`: API framework。
- `uvicorn[standard]`: local / production ASGI server。
- `pydantic-settings`: 環境変数ベースの settings。
- `httpx`: 外部 API / Agent 呼び出し。テストにも使う。

この repository では Firestore と ADK 実接続が runtime dependency である。

```toml
dependencies = [
  "google-adk",
  "google-cloud-aiplatform[agent-engines]",
  "google-cloud-firestore",
  "knowledge-drill-agent",
]
```

`knowledge-drill-agent` は `../agent` の editable path dependency。backend の mypy は `mypy_path = "../agent"` で agent package を解決する。

## Dev dependencies

標準 dev dependencies は次にする。

```toml
dev-dependencies = [
  "pytest",
  "pytest-asyncio",
  "ruff",
  "mypy",
]
```

- `pytest`: test runner。
- `pytest-asyncio`: async service / client test。
- `ruff`: format と lint。Black、isort、flake8 は標準では追加しない。
- `mypy`: 型チェック。

## pyproject.toml 方針

Python version は原則 3.11 以上にする。

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
ignore = []

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.11"
strict = true
plugins = []
```

Ruff に format と import sorting を寄せる。Black、isort、flake8 を重ねない。

## 実装ルール

### routes

- request validation、dependency 解決、service 呼び出し、response 変換だけを書く。
- business logic を書かない。
- 外部 API や DB SDK を直接呼ばない。
- route ごとに `APIRouter` を定義し、`main.py` で include する。

### services

- use case と business logic を置く。
- input / output は Pydantic model または明示型にする。
- FastAPI の `Request`、`Response`、`HTTPException` に依存しない。
- 失敗は application exception か typed result として表現する。

### clients

- 外部 API、Agent、DB SDK などの接続を閉じ込める。
- timeout を明示する。
- 外部レスポンスは client 境界で validation する。
- secret や endpoint は `config.py` から受け取る。
- `AgentRuntimeClient` が schema validation、retry、task latency logging、採点応答の文脈検証を持つ。
- `AdkAgentInvoker` は task 名から parentless leaf agent Runner への deterministic mapping を持つ。root_agent 転送は使わない。
- `LocalAgentInvoker` は認証なしの local / CI 用 fallback として維持する。

### repositories

- repository は永続化境界を閉じ込める。
- `InMemoryFirestoreClient` は local / test 用、`GoogleFirestoreClient` は Firestore 用。
- route や service から Google Firestore SDK を直接呼ばない。

### schemas.py

- Pydantic v2 を使う。
- `Any`、裸の `dict`、裸の `list` を避ける。
- request / response / service input / service output を明示する。
- 肥大化したら `schemas/` directory に分割する。

### config.py

- `pydantic-settings` で settings class を定義する。
- secret をコードにハードコードしない。
- `.env` を使う場合も実 secret を commit しない。
- `KNOWLEDGE_DRILLS_AGENT_MODE` は `local` / `adk`。既定は `local`。
- ADK mode では `GOOGLE_GENAI_USE_VERTEXAI` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION`、または `GOOGLE_API_KEY` が必要。

### errors.py

- application exception と API error response を定義する。
- route 内で例外を握りつぶさない。
- common error handler を `main.py` で登録する。

## ロギング

- `print` は使わない。
- 標準 `logging` を使う。
- MVP では `structlog` は標準追加しない。
- request id や structured logging が必要になった時点で追加を検討する。

## テスト

- route は FastAPI test client または `httpx` ベースの client でテストする。
- service は外部 client を fake / stub にして unit test する。
- client は timeout、error mapping、response validation をテストする。
- MVP でも health check と主要 API の正常系・代表的な異常系は追加する。

## 標準コマンド

作業後は実行できる範囲で次を確認する。

```bash
cd backend
uv run --frozen ruff check .
uv run --frozen mypy .
uv run --frozen pytest
```

依存関係が未 install、`uv` が未設定、外部 service credentials がないなどで実行できない場合は、実行不可理由と次に確認すべき事項を明示する。

## 分割するタイミング

MVP 構成が苦しくなったら、次の基準で分割する。

- `schemas.py` が大きくなったら `schemas/` に分割する。
- 永続化 logic が service から独立して増えたら `repositories/` を作る。
- 外部 API / SDK が複数種類に増えたら `clients/` を維持しつつ、必要に応じて `integrations/` に改名を検討する。
- 共通関数が 3 箇所以上で重複し、責務が明確な場合だけ専用 module を作る。曖昧な `utils/` は避ける。
