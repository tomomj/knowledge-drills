# knowledge-drills

Markdown 講座を実務シナリオ型ドリルに変換し、受講者の誤答から講座改善パッチを自動起案する
Knowledge CI アプリケーション。

## 構成

| ディレクトリ | 内容 |
|---|---|
| `backend/` | FastAPI（Cloud Run）。アプリの信頼境界: Firestore 更新・schema 検証・diff 生成 |
| `frontend/` | Vite + React + TypeScript |
| [`agent/`](agent/README.md) | Google ADK エージェント（ドリル生成 / 採点 / 誤答分析 / パッチ生成）+ eval |
| `terraform/` | Google Cloud インフラ（Cloud Run / Artifact Registry / WIF 等） |

## 開発

通常の開発操作はリポジトリ直下の `Makefile` から実行する。

| 目的 | コマンド |
|---|---|
| backend / frontend の dev server 起動 | `make dev` |
| backend の dev server 起動 | `make dev-backend` |
| frontend の dev server 起動 | `make dev-frontend` |
| 依存関係のインストール | `make install` |
| lint / typecheck / test | `make check` |
| test | `make test` |
| lint | `make lint` |
| typecheck | `make typecheck` |
| format | `make format` |
| frontend build | `make build-frontend` |

個別に確認する場合は次を使う。これらは外部接続・認証情報なしで成功することを前提にしている。

```sh
cd backend && uv run --frozen pytest && uv run --frozen ruff check . && uv run --frozen mypy .
cd agent   && uv run --frozen pytest && uv run --frozen ruff check . && uv run --frozen mypy .
cd frontend && npm test && npm run lint && npm run typecheck && npm run build
```

frontend は `npm` と `package-lock.json` を使う。主な npm scripts は `dev`、`test`、
`test:e2e`、`typecheck`、`build`、`lint`、`depcheck`、`knip`、`preview`。

Terraform は `terraform/` で管理する。通常の確認は `fmt`、`validate`、`plan` までとし、
`apply` はインフラ状態を変更するため明示的な実行判断を必要とする。

```sh
cd terraform
terraform fmt
terraform validate
terraform plan
```

Codex の project-local command rules は `.codex/rules/default.rules` に置く。この repository が
trusted のときだけ読み込まれ、通常の `uv` / `npm` / `make` / Terraform 確認コマンドを許可し、
`terraform apply` / `destroy` は拒否する。

CI は Backend / Frontend / Agent Eval で workflow を分け、該当ディレクトリに差分がある PR だけで
実行する。

- `.github/workflows/backend-ci.yml`: `backend/**` / `agent/**` の通常 CI
- `.github/workflows/frontend-ci.yml`: `frontend/**`
- `.github/workflows/agent-eval.yml`: `agent/**` 差分時に eval 専用 WIF で実 Gemini eval を実行する

`agent-eval.yml` は deploy 用 service account ではなく、Terraform が作成する
eval 専用 service account を使う。Terraform apply 後、repository variables に
`GCP_AGENT_EVAL_WORKLOAD_IDENTITY_PROVIDER` と `GCP_AGENT_EVAL_SERVICE_ACCOUNT` を設定する。

## Agent eval をローカルで回す

エージェントの出力品質は `adk eval` で回帰検証する（実 Gemini 呼び出しが発生。
1エージェントあたり1〜2分・数円程度）。CI では `agent/**` 差分時に
`.github/workflows/agent-eval.yml` が eval 専用 service account で同じ wrapper を実行する。
詳細な設計と全コマンドは
[`agent/evals/README.md`](agent/evals/README.md) を参照。

```sh
cd agent

# 認証（初回のみ）
gcloud auth application-default login
cp .env.example .env
# .env の GOOGLE_CLOUD_PROJECT を、Vertex AI で gemini-2.5-flash-lite を
# us-central1 から実行できるプロジェクトに変更する

# 全 eval を実行し、ADK の結果 JSON を読んで失敗時は非ゼロ終了する
python scripts/run_adk_evals.py
```

注意:

- `--isolated` は必須。省くと .venv に eval 依存（numpy 等）が残り、以後の `mypy .` が
  失敗する（復旧は `cd agent && uv sync --frozen`）。`scripts/run_adk_evals.py` は内部で
  `--isolated` を付けて実行する
- `adk eval` は eval 失敗時も exit code 0 を返すことがあるため、直接呼ばず
  `scripts/run_adk_evals.py` を使う
- 実行結果の詳細 JSON は `agent/evals/*/.adk/eval_history/` に保存される（gitignore 済み）
