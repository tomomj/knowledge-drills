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

各パッケージの検証コマンド（すべて外部接続・認証情報なしで成功する）:

```sh
cd backend && uv run --frozen pytest && uv run --frozen ruff check . && uv run --frozen mypy .
cd agent   && uv run --frozen pytest && uv run --frozen ruff check . && uv run --frozen mypy .
cd frontend && npm test && npm run lint
```

CI は Backend / Frontend / Agent で workflow を分け、該当ディレクトリに差分がある PR だけで
実行する。

- `.github/workflows/backend-ci.yml`: `backend/**`
- `.github/workflows/frontend-ci.yml`: `frontend/**`
- `.github/workflows/agent-ci.yml`: `agent/**`
- `.github/workflows/agent-eval.yml`: `main` への `agent/**` 差分 push 時に実 Gemini eval を実行する

## Agent eval をローカルで回す

エージェントの出力品質は `adk eval` で回帰検証する（実 Gemini 呼び出しが発生。
1エージェントあたり1〜2分・数円程度）。CI では `main` への `agent/**` 差分 push 時に
`.github/workflows/agent-eval.yml` が同じ wrapper を実行する。詳細な設計と全コマンドは
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
