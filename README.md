# knowledge-drills

Markdown 講座を実務シナリオ型ドリルに変換し、受講者の誤答から講座改善パッチを自動起案する
Knowledge CI アプリケーション。

## 構成

| ディレクトリ | 内容 |
|---|---|
| `backend/` | FastAPI（Cloud Run）。アプリの信頼境界: Firestore 更新・schema 検証・diff 生成 |
| `frontend/` | Vite + React + TypeScript |
| `agent/` | Google ADK エージェント（ドリル生成 / 採点 / 誤答分析 / パッチ生成）+ eval |
| `terraform/` | Google Cloud インフラ（Cloud Run / Artifact Registry / WIF 等） |

## 開発

各パッケージの検証コマンド（すべて外部接続・認証情報なしで成功する）:

```sh
cd backend && uv run --frozen pytest && uv run --frozen ruff check . && uv run --frozen mypy .
cd agent   && uv run --frozen pytest && uv run --frozen ruff check . && uv run --frozen mypy .
cd frontend && npm test && npm run lint
```

CI（`.github/workflows/ci.yml`）は PR ごとに Backend / Frontend / Agent の3ジョブで同じ検証を実行する。

## Agent eval をローカルで回す

エージェントの出力品質は `adk eval` で回帰検証する（実 Gemini 呼び出しが発生。
1エージェントあたり1〜2分・数円程度）。詳細な設計と全コマンドは
[`agent/evals/README.md`](agent/evals/README.md) を参照。

```sh
cd agent

# 認証（初回のみ）
gcloud auth application-default login
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=<your-project>
export GOOGLE_CLOUD_LOCATION=us-central1

# 例: grading の eval（drill_generator / failure_analysis / document_patch も同形式）
PYTHONPATH=. uv run --isolated --frozen --group eval adk eval \
  evals/grading evals/grading/grading.evalset.json \
  --config_file_path evals/grading/test_config.json \
  --print_detailed_results
```

注意:

- `--isolated` は必須。省くと .venv に eval 依存（numpy 等）が残り、以後の `mypy .` が
  失敗する（復旧は `cd agent && uv sync --frozen`）
- `PYTHONPATH=.` も必須（isolated 環境にはプロジェクト自身がインストールされないため）
- 実行結果の詳細 JSON は `agent/evals/*/.adk/eval_history/` に保存される（gitignore 済み）
