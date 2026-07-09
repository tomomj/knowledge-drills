# Agent

`agent/` は Knowledge Drills の Google ADK agent package です。講座 Markdown から
実務シナリオ型ドリルを生成し、受講者回答の採点、誤答傾向の分析、講座改善パッチ案の
作成を担います。

backend からは `knowledge-drill-agent` として editable path dependency で import されます。
実行時は root agent に転送せず、backend が task 名ごとに parentless leaf agent を直接
`Runner` で呼び出します。

## 構成

| パス | 内容 |
|---|---|
| `knowledge_drill_agent/agent.py` | `root_agent` と4つの leaf agent factory |
| `knowledge_drill_agent/config.py` | model、Vertex AI project/location、分析モードの解決 |
| `knowledge_drill_agent/schemas.py` | Agent 入出力の Pydantic schema |
| `knowledge_drill_agent/prompts/*.md` | 各 Agent の instruction |
| `knowledge_drill_agent/sample_outputs/*.json` | backend contract 互換性テスト用のサンプル出力 |
| `evals/` | `adk eval` 用の evalset と judge rubric |
| `scripts/run_adk_evals.py` | eval 結果 JSON を読んで失敗時に非ゼロ終了する wrapper |
| `tests/` | schema、factory、eval asset、backend contract の通常テスト |

## Agent 一覧

| Agent | backend task | 入力 | 出力 | 役割 |
|---|---|---|---|---|
| `drill_generator_agent` | `generate_drill` | `DrillGenerationInput` | `DrillGenerationOutput` | 講座 Markdown から記述式ドリルを3問生成する |
| `grading_agent` | `grade_answer` | `GradingInput` | `GradingOutput` | 1つの受講者回答を rubric に基づいて採点する |
| `failure_analysis_agent` | `analyze_failures` | `FailureAnalysisInput` | `FailureAnalysisOutput` | 採点済み回答から共通する誤答傾向を抽出する |
| `document_patch_agent` | `propose_document_patch` | `DocumentPatchInput` | `DocumentPatchOutput` | 誤答傾向に対応する講座 Markdown 改善案を作る |

`root_agent` は ADK discovery 用の入口です。share token、Firestore 状態、status 遷移、
diff 生成、patch の apply/reject は backend の責務です。

## 契約

- `knowledge_drill_agent/schemas.py` が JSON 契約の source of truth です。
- JSON は camelCase serialization を維持します。
- `DrillGenerationOutput.questions` は3問固定です。
- 各 `DrillQuestion.rubric` の points 合計は `maxScore` と一致させます。
- `GradingOutput.score` は `maxScore` を超えません。
- `FailureSignal.severity` は `low` / `medium` / `high` のみです。
- `FailureSignal.affectedCount` はその誤答傾向を示した受講者数、`sampleSize` は採点済み回答の受講者総数です。
- prompt だけで直せる品質問題は `knowledge_drill_agent/prompts/*.md` で直し、schema や
  backend contract を不用意に変えません。
- `sample_outputs/*.json` を変える場合は backend の契約テストへの影響も確認します。

## ローカル実行

```sh
cd agent
uv sync
```

通常の静的検証は認証情報なしで実行できます。

```sh
uv run --native-tls --frozen pytest
uv run --native-tls --frozen ruff check .
uv run --native-tls --frozen mypy .
```

repository root からは次でも実行できます。

```sh
make test-agent
make lint-agent
make typecheck-agent
```

## 実モデル eval

実 Gemini 呼び出しを含む eval は wrapper 経由で実行します。`adk eval` を直接呼ぶと、
eval 失敗時も exit code 0 になることがあります。

```sh
cd agent
cp .env.example .env
# .env の GOOGLE_CLOUD_PROJECT を有効な GCP project に変更する
python scripts/run_adk_evals.py
python scripts/run_adk_evals.py --profile quick
```

標準の `.env.example` は Vertex AI を使います。

| 変数 | 用途 |
|---|---|
| `GOOGLE_GENAI_USE_VERTEXAI` | `TRUE` の場合は Vertex AI を使う |
| `GOOGLE_CLOUD_PROJECT` | Vertex AI を実行する GCP project |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI location。現行既定は `global` |
| `KNOWLEDGE_DRILL_AGENT_MODEL` | leaf agent の model。現行既定は `gemini-3.1-flash-lite` |
| `KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE` | failure analysis の実行モード |

AI Studio を使う場合は `GOOGLE_API_KEY` でも動きます。eval 依存は通常の `.venv` に入れず、
`scripts/run_adk_evals.py` が内部で `uv run --native-tls --isolated --frozen --group eval`
を使います。

## メンテナンス

- leaf agent factory は `parent_agent is None` を維持します。
- backend の deterministic task mapping と task 名をずらしません。
- prompt、schema、sample output、evalset は同じ契約を共有します。
- 実モデル eval が認証や quota で実行できない場合も、通常テストと
  `tests/test_evals_assets.py` は通る状態を保ちます。
