# Backend

`backend/` は Knowledge Drills の FastAPI API です。講座、ドリル、回答、分析、講座改善パッチの
信頼境界を担い、Firestore 更新、schema 検証、Agent 呼び出し、diff 生成、認証をここで扱います。

ローカル既定では in-memory repository、local agent、認証なしで起動します。本番では Terraform が
Firestore、Firebase auth、ADK agent、Cloud Trace を有効にした Cloud Run 環境変数を設定します。

## 構成

| パス | 内容 |
|---|---|
| `app/main.py` | FastAPI app factory、middleware、repository/service wiring |
| `app/config.py` | `KNOWLEDGE_DRILLS_` prefix の settings |
| `app/schemas.py` | API と service の Pydantic schema |
| `app/errors.py` | application exception と API error handler |
| `app/routes/` | HTTP route。validation と service 呼び出しに留める |
| `app/services/` | use case と business logic |
| `app/repositories/` | Firestore / in-memory persistence boundary |
| `app/clients/` | ADK agent、local agent、Firebase auth client |
| `app/observability.py` | ADK trace export 設定 |
| `app/utils/diff.py` | Markdown patch review 用 diff helper |
| `tests/` | route、service、client、contract、repository のテスト |
| `scripts/manual_adk_smoke.py` | ADK 実接続の手動 smoke check |

## API

| Endpoint | 用途 |
|---|---|
| `GET /health` | health check |
| `GET /api/me` | 現在の owner user |
| `/api/courses` | 講座作成、一覧、取得、更新、改訂履歴、diff |
| `/api/courses/{courseId}/drill-runs` | 講座オーナー向けドリル生成、取得、回答一覧、分析開始 |
| `/api/drills/{shareToken}` | 受講者向けドリル取得、回答送信 |
| `/api/patches/{patchId}` | 講座改善パッチの取得、apply、reject |

詳細な request / response 契約は `app/schemas.py` が source of truth です。

## ローカル実行

```sh
cd backend
uv sync
uv run --native-tls --frozen uvicorn app.main:app --host 127.0.0.1 --port 8000
```

repository root からは次も使えます。

```sh
make dev-backend
make serve-backend
```

frontend と同時に動かす場合は root で `make dev` を使います。

## 環境変数

`app/config.py` は `.env` と環境変数を読みます。通常のアプリ設定は
`KNOWLEDGE_DRILLS_` prefix です。

| 変数 | 既定 | 用途 |
|---|---|---|
| `KNOWLEDGE_DRILLS_ENVIRONMENT` | `dev` | 実行環境名 |
| `KNOWLEDGE_DRILLS_STORAGE_MODE` | `memory` | `memory` または `firestore` |
| `KNOWLEDGE_DRILLS_FIRESTORE_DATABASE` | `(default)` | Firestore database ID |
| `KNOWLEDGE_DRILLS_AGENT_MODE` | `local` | `local` または `adk` |
| `KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS` | `60` | Agent 呼び出し timeout |
| `KNOWLEDGE_DRILLS_AGENT_TRACE_EXPORTER` | `none` | `none`、`otlp`、`gcp` |
| `KNOWLEDGE_DRILLS_AUTH_MODE` | `none` | `none` または `firebase` |
| `KNOWLEDGE_DRILLS_FIREBASE_PROJECT_ID` | 未指定 | Firebase auth project |
| `KNOWLEDGE_DRILLS_CORS_ALLOWED_ORIGINS` | local Vite origins | CORS 許可 origin のカンマ区切り |

`KNOWLEDGE_DRILLS_AGENT_MODE=adk` の場合は、ADK 側の認証環境も必要です。

| 変数 | 用途 |
|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI=TRUE` | Vertex AI を使う |
| `GOOGLE_CLOUD_PROJECT` | Vertex AI を実行する GCP project |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI location |
| `GOOGLE_API_KEY` | Vertex AI を使わない場合の代替 |
| `KNOWLEDGE_DRILL_AGENT_MODEL` | agent package が解決する model |

`KNOWLEDGE_DRILLS_AGENT_TRACE_EXPORTER=otlp` の場合は
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` または `OTEL_EXPORTER_OTLP_ENDPOINT` も必要です。

## 検証コマンド

```sh
uv run --native-tls --frozen pytest
uv run --native-tls --frozen ruff check .
uv run --native-tls --frozen mypy .
```

repository root からは `make test-backend`、`make lint-backend`、`make typecheck-backend` を
使えます。

ADK 実接続を確認する場合は、認証環境を設定したうえで手動 smoke script を使います。

```sh
uv run --native-tls --frozen python scripts/manual_adk_smoke.py
```

## 実装ルール

- route は薄く保ち、Firestore SDK や外部 API SDK を直接呼びません。
- business logic は `services/` に置きます。
- 永続化は `repositories/` に閉じ込めます。
- Agent 実行は `AgentRuntimeClient` と invoker が担当し、response schema validation もここで行います。
- `AdkAgentInvoker` は task 名から parentless leaf agent Runner へ deterministic に mapping します。
- `LocalAgentInvoker` は認証なしの local / CI fallback として維持します。
- secret や credentials はコードに書きません。
