# Agent

`agent/` は Knowledge Drills の Google ADK agent app。講座 Markdown からドリルを作り、
受講者回答を採点し、誤答傾向を分析して、講座改善パッチ案を作る。

実装上は `knowledge_drill_agent.agent` に root agent と4つの leaf agent を定義する。
バックエンドからの実行時は root agent に処理を委譲せず、task 名ごとに対応する leaf agent を
直接 `Runner` で呼び出す。

## 構成

| パス | 内容 |
|---|---|
| `knowledge_drill_agent/agent.py` | root agent と4つの leaf agent の定義 |
| `knowledge_drill_agent/schemas.py` | 各 Agent の Pydantic 入出力 schema |
| `knowledge_drill_agent/prompts/*.md` | 各 Agent の instruction |
| `knowledge_drill_agent/sample_outputs/*.json` | backend contract 互換性テスト用のサンプル出力 |
| `evals/` | `adk eval` 用の evalset と LLM Judge rubric |
| `scripts/run_adk_evals.py` | 全 eval 実行用 wrapper |

## Agent 一覧

| Agent | backend task | 入力 | 出力 | 役割 |
|---|---|---|---|---|
| `drill_generator_agent` | `generate_drill` | `DrillGenerationInput` | `DrillGenerationOutput` | 講座 Markdown から実務シナリオ型の記述問題を3問生成する |
| `grading_agent` | `grade_answer` | `GradingInput` | `GradingOutput` | 1つの受講者回答を、設問 rubric と回答本文だけに基づいて採点する |
| `failure_analysis_agent` | `analyze_failures` | `FailureAnalysisInput` | `FailureAnalysisOutput` | 採点済み回答の集合から、繰り返し発生している誤答傾向を抽出する |
| `document_patch_agent` | `propose_document_patch` | `DocumentPatchInput` | `DocumentPatchOutput` | 検証済みの誤答傾向に対応する最小限の講座 Markdown 改善案を作る |

`root_agent` は ADK agent app としての入口を表す。実行時の信頼境界は backend 側にあり、
share token、Firestore 状態、status 遷移、diff 生成、patch の apply/reject は Agent の責務ではない。

## `drill_generator_agent`

講座 Markdown から、実務判断を問う記述式ドリルを3問生成する Agent。

入力:

- `courseTitle`
- `courseMarkdown`

出力:

- `questions`: 3件固定
- 各 question は `id`、`question`、`intent`、`rubric`、`idealAnswer`、`sourceEvidence`、`maxScore` を持つ

主な制約:

- 用語定義や暗記を直接聞く問題ではなく、実務シナリオで判断理由を書かせる
- 各問題の `maxScore` は4点
- 各問題の rubric points 合計は必ず4点
- `sourceEvidence` は講座 Markdown 内の実在する見出し・抜粋に基づく
- 講座 Markdown にないルール、数値、前提を問わない

## `grading_agent`

受講者の1回答を採点する Agent。採点対象は1問分だけで、集計や保存は backend が行う。

入力:

- `question`: `DrillQuestion`
- `learnerAnswer`

出力:

- `questionId`
- `score`
- `maxScore`
- `correctPoints`
- `missingPoints`
- `feedback`
- `failureTags`

主な制約:

- 入力の rubric、ideal answer、source evidence、learner answer だけを根拠にする
- 受講者が書いていない内容を推測・補完して加点しない
- 短い回答も受け付けるが、足りない reasoning は `missingPoints` と `score` に反映する
- `score` は `maxScore` を超えない
- `failureTags` は `missing_evidence` や `unclear_condition` のような具体的な不足概念にする

## `failure_analysis_agent`

複数の採点済み回答から、繰り返し発生している失敗傾向を Failure Signal として抽出する Agent。
単発のミスより、複数回答にまたがるパターンを優先する。

入力:

- `courseMarkdown`
- `questions`
- `answers`
- `gradingResults`

出力:

- `failureSignals`
- 各 signal は `id`、`title`、`severity`、`evidence`、`likelyCause`、
  `suspectedDocumentGap`、`targetSections`、`recommendedChange`、`affectedCount`、
  `sampleSize`、`confidenceNote` を持つ

主な制約:

- 孤立したミスより、繰り返し発生しているパターンを優先する
- `affectedCount` はその誤答傾向を示した受講者数、`sampleSize` は採点済み回答の受講者総数にする
- `sampleSize` が3未満の場合は `confidenceNote` を含め、小標本の傾向として表現する
- 受講者の理解不足と、資料側の説明不足を区別する
- 受講者を責める表現を避ける
- 講座 Markdown にない社内ルール、事実、義務を作らない

## `document_patch_agent`

Failure Signal に対応する講座 Markdown の改善案を作る Agent。実際に適用するかどうかは
backend と講座オーナーが決める。

入力:

- `courseMarkdown`
- `failureSignals`

出力:

- `patchedMarkdown`
- `patchSummary`
- `riskNotes`

主な制約:

- Failure Signal に対応する最小限の変更に留める
- 既存の Markdown 構造をできるだけ維持する
- 無関係なセクションを書き換えない
- 講座にないルールや根拠のない事実を追加しない
- 不確かな内容、小さいサンプルサイズ、オーナー判断が必要な点は `riskNotes` に書く
- patch が適用済みだとは主張しない

## 実行と検証

通常の静的検証:

```sh
cd agent
uv run --native-tls --frozen pytest
uv run --native-tls --frozen ruff check .
uv run --native-tls --frozen mypy .
```

実モデル eval:

```sh
cd agent
python scripts/run_adk_evals.py
```

eval の内容は `evals/README.md` を参照する。実モデル eval は Gemini 呼び出しが発生するため、
認証情報と利用可能な Google Cloud または API key が必要。
