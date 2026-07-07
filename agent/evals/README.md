# Agent Evals

4エージェントそれぞれの品質を `adk eval` で回帰検証するための最小 eval セット。
**評価項目は各エージェント最大2つ**に絞っている。

## 構成

| Agent | 評価項目 | 検証内容 |
|---|---|---|
| `grading` | `final_response_match_v2` + rubric | ゴールデン採点との一致（満点 / 部分点 / rubric 外は加点しない）、回答にないことを補完しない |
| `failure_analysis` | rubric のみ | 仕込んだ共通誤答（4人中3人が事前承認に言及せず）の検出をルーブリックで判定、confidenceNote・表現の節度 |
| `drill_generator` | rubric のみ | 実務シナリオ型であること、講座 Markdown への根拠性（生成に多様性があるためゴールデン一致は不採用） |
| `document_patch` | rubric のみ | 最小変更・ルール創作なし・riskNotes（全文一致は brittle なため不採用） |

各ディレクトリは `adk eval` が認識するエージェントパッケージになっており、
`agent.py` がスタンドアロンファクトリ（親なし）から `root_agent` を公開する。
`test_config.json` は evalset と同じディレクトリに置くと自動で読まれる。

## 実行方法

実 Gemini 呼び出し（対象エージェント + LLM judge）が発生するため、認証情報が必要。
eval 依存は既定環境に入れていないので `--isolated --group eval` を付ける
（`--isolated` を省くと .venv に numpy 等が残り、以後の `mypy .` が numpy 型スタブの
Python 3.12+ 構文で失敗する。残ってしまった場合は `uv sync --frozen` で復旧できる）。

```sh
cd agent

# 認証は Vertex AI が正道（API キー不要。プロジェクトのモデル実行基盤に一致）
gcloud auth application-default login   # ローカルの場合。CI では cd.yml の WIF 認証をそのまま利用
export GOOGLE_GENAI_USE_VERTEXAI=TRUE
export GOOGLE_CLOUD_PROJECT=...
export GOOGLE_CLOUD_LOCATION=us-central1
# （代替: AI Studio を使うなら GOOGLE_API_KEY=... でも動く）

PYTHONPATH=. uv run --isolated --frozen --group eval adk eval evals/grading evals/grading/grading.evalset.json \
  --config_file_path evals/grading/test_config.json --print_detailed_results

PYTHONPATH=. uv run --isolated --frozen --group eval adk eval evals/drill_generator evals/drill_generator/drill_generator.evalset.json \
  --config_file_path evals/drill_generator/test_config.json --print_detailed_results

PYTHONPATH=. uv run --isolated --frozen --group eval adk eval evals/failure_analysis evals/failure_analysis/failure_analysis.evalset.json \
  --config_file_path evals/failure_analysis/test_config.json --print_detailed_results

PYTHONPATH=. uv run --isolated --frozen --group eval adk eval evals/document_patch evals/document_patch/document_patch.evalset.json \
  --config_file_path evals/document_patch/test_config.json --print_detailed_results
```

CI/CD への組み込みは cd.yml（main push、WIF 認証済み）のデプロイ前ゲートを想定。
PR CI は認証情報なしを維持する（`tests/test_evals_assets.py` がアセットの構造のみ検証する）。

## 閾値の校正記録

- 2026-07-07 に Vertex AI（gemini-2.5-flash）で全4 eval を実行。grading 3/3・drill_generator 1/1・
  document_patch 1/1 合格。failure_analysis は `final_response_match_v2` が実行ごとに
  合格/不合格が割れた（分析系は出力の構成・表現の自由度が高く、ゴールデン全体一致が不安定）。
  → match メトリクスを外し、「仕込んだ共通誤答を検出できたか」を rubric の1項目として
  判定する方式に変更（rubric のみ・3項目）。この構成での実モデル再検証は未実施。
  プロンプト自体も未チューニングのため、閾値・ルーブリックは CI 組み込み時に再校正する。

## モデル

コストカットのため、評価対象エージェント（`KNOWLEDGE_DRILL_AGENT_MODEL` のデフォルト）と
LLM judge（各 test_config.json の `judge_model_options`）は **`gemini-2.5-flash-lite`** に統一
（2026-07-07 決定。Terraform の Cloud Run 環境変数も同モデルで、本番と一致）。
judge と被評価者が同一モデルである点は自己肯定バイアスの懸念があるため、
CI ゲート本格運用時に judge のみ上位モデルへの変更を検討する。

## メンテナンス

- evalset の入力・ゴールデンは `knowledge_drill_agent/schemas.py` の camelCase シリアライズに
  一致させること（ADK の input_schema 強制により、逸脱すると即失敗する）
- プロンプトを変更したら該当エージェントの eval を回してから main に入れる
- improvement_agent（自律型）導入時は `tool_trajectory_avg_score` と
  `rubric_based_tool_use_quality_v1` のケースをここに追加する
