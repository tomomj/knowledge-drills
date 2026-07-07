# Agent Evals

4エージェントそれぞれの品質を `adk eval` で回帰検証するための最小 eval セット。
ADK の `criteria` は各エージェント最大2つに絞る。現行はすべて
`rubric_based_final_response_quality_v1` 1つだけを使い、その中の `rubrics` で
具体的な合格条件を定義する。

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

## テスト項目

`*.evalset.json` は Agent に渡す入力ケース、`test_config.json` は LLM judge に渡す
rubric を定義する。現在の metric はすべて `rubric_based_final_response_quality_v1`
なので、evalset の `final_response` はゴールデン参考値として残しているが、合否は
`test_config.json` の rubric 判定で決まる。

### `grading`

ファイル:

- `evals/grading/grading.evalset.json`
- `evals/grading/test_config.json`

共通入力は「取引先2名との会食で1人あたり7,000円のコースを予約する」ケース。
rubric は「5,000円上限超過の識別」2点と「事前に部門長の承認を得る対応」2点。

| eval_id | 入力の狙い | 期待する振る舞い |
|---|---|---|
| `grading_full_score` | 受講者が上限超過と事前承認の両方を書いている | `score=4`。両 rubric を `correctPoints` に入れ、補完なしで満点にする |
| `grading_partial_score` | 受講者が上限超過だけを書き、事前承認を書いていない | `score=2`。事前承認を `missingPoints` に入れ、回答にない内容を補って加点しない |
| `grading_off_rubric_no_credit` | 受講者が領収書提出だけを書いている | `score=0`。講座内の別ルールに合っていても、この設問 rubric 外なので加点しない |

Judge rubric:

- 採点は受講者の回答に実際に書かれている内容だけを根拠にしており、回答に書かれていないことを補って加点していない。
- `correctPoints` と `missingPoints` が入力 rubric の基準に対応しており、rubric にない基準で加点・減点していない。
- `score` は受講者が満たした rubric points の合計に一致し、`maxScore` は入力 `question.maxScore` と一致している。

### `drill_generator`

ファイル:

- `evals/drill_generator/drill_generator.evalset.json`
- `evals/drill_generator/test_config.json`

入力は「経費精算の判断基準」の講座 Markdown。事前承認、交際費、領収書の3セクションを含む。
生成問題はモデル出力の多様性が高いため、全文一致では評価しない。

| eval_id | 入力の狙い | 期待する振る舞い |
|---|---|---|
| `dg_expense_course` | 経費精算ルールからドリルを生成する | 3問すべてを実務シナリオ型にし、講座 Markdown に存在する記述だけを根拠にする |

Judge rubric:

- 生成された3問すべてが実務シナリオ型で、用語の定義や暗記を直接尋ねる問題が含まれておらず、受講者に判断理由を書かせる問いになっている。
- すべての問題・`idealAnswer`・`sourceEvidence` が入力の講座 Markdown に実在する記述に根拠を持ち、講座に書かれていないルールや数値を問うていない。

### `failure_analysis`

ファイル:

- `evals/failure_analysis/failure_analysis.evalset.json`
- `evals/failure_analysis/test_config.json`

入力は同じ経費精算講座、設問、4人分の採点済み回答。4人中3人が
「上限超過は識別できたが、事前に部門長の承認を得る対応を書けなかった」
という共通誤答を仕込んでいる。

| eval_id | 入力の狙い | 期待する振る舞い |
|---|---|---|
| `fa_detects_planted_common_error` | 仕込んだ共通誤答を分析で拾えるかを見る | `failureSignals` に事前承認漏れの傾向を出し、対象セクションを `交際費` として示す |

Judge rubric:

- `failureSignals` のいずれかが、複数の受講者（4人中3人）が交際費の上限超過時に事前に部門長の承認を得るという対応に言及できなかった、という共通誤答傾向を指摘しており、`targetSections` に交際費セクションが含まれている。
- 回答数が少ない場合に `sampleSize` を正しく報告し、`confidenceNote` で断定を避けて傾向として表現している。
- 受講者を責める表現がなく、資料の説明不足（`suspectedDocumentGap`）と受講者の理解不足（`likelyCause`）を区別して記述している。

### `document_patch`

ファイル:

- `evals/document_patch/document_patch.evalset.json`
- `evals/document_patch/test_config.json`

入力は経費精算講座 Markdown と、`failure_analysis` 相当の
「交際費の上限超過時に事前承認が抜ける」failure signal。
パッチ本文は表現揺れがあるため、全文一致では評価しない。

| eval_id | 入力の狙い | 期待する振る舞い |
|---|---|---|
| `dp_prior_approval_gap` | 事前承認漏れの分析結果から講座改善パッチを作れるかを見る | `交際費` セクションに絞って最小変更し、既存講座から安全に明確化できる範囲に留める |

Judge rubric:

- `patchedMarkdown` の変更が `failureSignals` の `targetSections` に対応する最小限に留まり、無関係なセクションの内容や見出し構造を書き換えていない。
- 講座に存在しない社内ルールや数値を新しく作っておらず、既存の記述から安全に明確化できる範囲で修正し、不確かな内容は `riskNotes` に明示している。

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

通常の Agent CI は認証情報なしで `tests/test_evals_assets.py` によるアセット構造検証まで行う。
実モデル eval は `.github/workflows/agent-eval.yml` が `main` への `agent/**` 差分 push 時に Vertex AI 認証付きで
実行する。`adk eval` は eval 失敗時も exit code 0 を返すことがあるため、自動化では必ず
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
