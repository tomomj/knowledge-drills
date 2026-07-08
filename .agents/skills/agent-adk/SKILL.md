---
name: agent-adk
description: Knowledge Drills の agent/ 配下で Google ADK agent、Pydantic schema、prompt、sample_outputs、ADK eval、Agent Runtime 連携を実装・レビュー・テストするときに使う。特に create_*_agent の parentless leaf agent、root_agent、KNOWLEDGE_DRILL_AGENT_MODEL、camelCase schema、uv、pytest、ruff、mypy、scripts/run_adk_evals.py、google-adk[eval] の isolated 実行を判断するときに使う。
---

# Agent ADK

Knowledge Drills の `agent/` は Google ADK agent package であり、backend から editable path dependency として import される。prompt、schema、sample output、eval asset の契約を壊さないことを優先する。

## 構成

```text
agent/
├── pyproject.toml
├── knowledge_drill_agent/
│   ├── agent.py
│   ├── config.py
│   ├── schemas.py
│   ├── samples.py
│   ├── prompts/
│   └── sample_outputs/
├── evals/
│   ├── grading/
│   ├── drill_generator/
│   ├── failure_analysis/
│   └── document_patch/
├── scripts/run_adk_evals.py
└── tests/
```

## Agent 実装ルール

- `agent.py` は4つの leaf agent factory を公開する: `create_drill_generator_agent` / `create_grading_agent` / `create_failure_analysis_agent` / `create_document_patch_agent`。
- backend の in-process Runner は root transfer を使わず、parentless leaf agent を個別実行する。factory の `parent_agent is None` を維持する。
- module-level の `root_agent` は ADK discovery 用に維持するが、backend の deterministic task mapping では使わない。
- model 名は `KNOWLEDGE_DRILL_AGENT_MODEL` から解決する。コードに個別 model を散らさない。
- prompt は `knowledge_drill_agent/prompts/*.md` が所有する。schema や backend contract を変えずに prompt だけで直せる問題は prompt 側で直す。

## Schema 契約

- schema は `knowledge_drill_agent/schemas.py` の Pydantic model が source of truth。
- JSON は camelCase serialization を維持する。backend 互換と ADK input_schema 強制のため、evalset の user text も schema-valid JSON 文字列にする。
- `DrillGenerationOutput.questions` は必ず3問。
- `DrillQuestion.rubric` の points 合計は `maxScore` と一致させる。
- `GradingOutput.score <= maxScore` を守る。questionId / score 上限の文脈検証は backend 側にもあるため、agent 出力でも逸脱しない。
- `sample_outputs/*.json` を変える場合は backend の契約テストも影響確認する。

## Eval 運用

- 実モデル eval は `python scripts/run_adk_evals.py` を使う。`adk eval` を直接呼ぶと、失敗時も exit code 0 になることがある。
- `scripts/run_adk_evals.py` は `.env` を読み、`uv run --native-tls --isolated --frozen --group eval adk eval ...` を実行し、`.adk/eval_history/*.evalset_result.json` を読んで失敗判定する。
- `agent/.env.example` の標準は Vertex AI `GOOGLE_CLOUD_LOCATION=us-central1` と `KNOWLEDGE_DRILL_AGENT_MODEL=gemini-2.5-flash-lite`。
- `google-adk[eval]` は eval group のみ。通常 `.venv` を汚さないため、eval は必ず isolated 実行にする。
- PR CI は認証なしを維持する。credential-free guard は `tests/test_evals_assets.py`。
- grading / drill_generator / failure_analysis / document_patch の eval は各ディレクトリの `agent.py` が parentless `root_agent` を公開する。

## テストと検証

認証なしで通常確認する:

```bash
cd agent
uv run --native-tls --frozen pytest
uv run --native-tls --frozen ruff check .
uv run --native-tls --frozen mypy .
```

実 Gemini eval を確認する:

```bash
cd agent
cp .env.example .env
# GOOGLE_CLOUD_PROJECT を有効な GCP project に変更
python scripts/run_adk_evals.py
```

外部接続や認証がない環境では、実 eval を実行不可として理由を明示し、少なくとも `tests/test_evals_assets.py` を通す。
