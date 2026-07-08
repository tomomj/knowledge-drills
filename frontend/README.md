# Frontend

`frontend/` は Knowledge Drills の Vite + React + TypeScript アプリです。講座オーナー向けの
講座編集、ドリル管理、回答分析、パッチ確認画面と、受講者向けの共有ドリル画面を提供します。

## 構成

| パス | 内容 |
|---|---|
| `src/app/` | router と app entry component |
| `src/pages/` | route component と page-level orchestration |
| `src/components/common/` | 再利用する presentational component |
| `src/api/` | HTTP client と API request/response type |
| `src/lib/` | auth helper、runtime helper、pure helper |
| `src/auth/` | owner 認証 provider と gate |
| `e2e/` | Playwright の主要 workflow |
| `tests/` | build 設定などの補助テスト |

## 画面

| Route | 用途 |
|---|---|
| `/courses` | 講座一覧 |
| `/courses/new` | 講座作成 |
| `/courses/:courseId` | 講座編集 |
| `/courses/:courseId/history` | 講座改訂履歴 |
| `/courses/:courseId/drill-runs/:drillRunId` | ドリル管理と回答確認 |
| `/courses/:courseId/drill-runs/:drillRunId/analysis` | 分析結果とパッチ確認 |
| `/patches/:patchId` | パッチ確認 |
| `/drills/:shareToken` | 受講者向け共有ドリル |

## ローカル実行

```sh
cd frontend
npm install
npm run dev
```

Vite dev server は既定で `/api` を `http://127.0.0.1:8000` に proxy します。backend と
frontend を同時に起動する場合は repository root から次を使えます。

```sh
make dev
```

Firebase を使わずにオーナー画面を触る場合は local auth を有効にします。

```sh
VITE_AUTH_MODE=none npm run dev
```

## 環境変数

| 変数 | 用途 |
|---|---|
| `VITE_API_BASE_URL` | API の base URL。未指定時は同一 origin の `/api` を使う |
| `VITE_AUTH_MODE=none` | Firebase を使わず local owner として動かす |
| `VITE_FIREBASE_API_KEY` | Firebase Authentication の API key |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase Authentication の auth domain |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project ID |
| `VITE_FIREBASE_APP_ID` | Firebase app ID |

Playwright は `VITE_AUTH_MODE=none` を指定して frontend を起動し、backend には
`KNOWLEDGE_DRILLS_CORS_ALLOWED_ORIGINS` を渡します。

## 検証コマンド

```sh
npm test
npm run lint
npm run typecheck
npm run build
```

必要に応じて次も実行します。

```sh
npm run depcheck
npm run knip
npm run test:e2e
```

repository root からは `make test-frontend`、`make lint-frontend`、`make typecheck-frontend`、
`make build-frontend` も使えます。

## 実装ルール

- `pages/` は API 呼び出し、local page state、submit handler を持ちます。
- `components/` は data を props で受け取り、user intent を callback で外へ出します。
- `components/` から `api/` を import しません。
- `api/` は HTTP と API type を持ち、画面固有の状態管理を持ちません。
- `lib/` は小さく保ち、React render に依存する処理を置きません。
- 受講者画面に `rubric` や `idealAnswer` を表示しません。
- invalid share token、stale patch、patch conflict、server failure は page state として区別します。
