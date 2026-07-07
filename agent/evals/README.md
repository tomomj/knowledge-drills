# Agent Evals

4エージェントそれぞれの品質を `adk eval` で回帰検証するための最小 eval セット。
**評価項目は各エージェント最大2つ**に絞っている。

## 構成

| Agent | 評価項目 | 検証内容 |
|---|---|---|
| `grading` | rubric のみ | 満点 / 部分点 / rubric 外は加点しない、回答にないことを補完しない、score が rubric points と一致する |
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
cp .env.example .env
# .env の GOOGLE_CLOUD_PROJECT を、Vertex AI で gemini-2.5-flash-lite を
# us-central1 から実行できるプロジェクトに変更する
# （代替: AI Studio を使うなら GOOGLE_API_KEY=... でも動く）

python scripts/run_adk_evals.py
```

PR CI は認証情報なしを維持する（`tests/test_evals_assets.py` がアセットの構造のみ検証する）。
`adk eval` は eval 失敗時も exit code 0 を返すことがあるため、自動化する場合は必ず
結果 JSON を読む `scripts/run_adk_evals.py` を経由する。

## 閾値の校正記録

- 2026-07-07 に Vertex AI（gemini-2.5-flash）で全4 eval を実行。grading 3/3・drill_generator 1/1・
  document_patch 1/1 合格。failure_analysis は `final_response_match_v2` が実行ごとに
  合格/不合格が割れた（分析系は出力の構成・表現の自由度が高く、ゴールデン全体一致が不安定）。
  → match メトリクスを外し、「仕込んだ共通誤答を検出できたか」を rubric の1項目として
  判定する方式に変更（rubric のみ・3項目）。
- 2026-07-07 に Vertex AI（gemini-2.5-flash-lite / us-central1）で
  `scripts/run_adk_evals.py` 経由の現行構成を再検証。grading 3/3・drill_generator 1/1・
  failure_analysis 1/1・document_patch 1/1 合格。grading は `feedback` / `failureTags` の
  表現揺れで `final_response_match_v2` が brittle だったため、rubric-only に変更し、
  score と maxScore の整合性 rubric を追加した。

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
