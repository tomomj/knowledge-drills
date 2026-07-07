# Agent Evals

4エージェントそれぞれの品質を `adk eval` で回帰検証するための最小 eval セット。
現行はすべて `rubric_based_final_response_quality_v1` 1つだけを使い、その中の
`rubrics` も各エージェント1つの統合 rubric に絞る。PR CI では細かい診断よりも
安定した green/red 判定を優先する。

入力ケースは「経費精算」「情報セキュリティ」「勤怠・休暇申請」の3ジャンルを
カバーする。経費精算と情報セキュリティは drill 生成 → 採点 → 失敗分析 → 講座パッチ
の4エージェント縦断で同一シナリオを共有し、単一ジャンルへの過学習
（rubric・プロンプトがそのジャンルの語彙に依存すること）を検出できるようにしている。

## 構成

| Agent | 評価項目 | 検証内容 |
|---|---|---|
| `grading` | rubric のみ | 満点 / 部分点 / rubric 外は加点しない、回答にないことを補完しない、score が rubric points と一致する |
| `failure_analysis` | rubric のみ | 仕込んだ共通誤答（4人中3人が同じ対応を書けない）の検出をルーブリックで判定、confidenceNote・表現の節度 |
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

経費精算ジャンルの共通入力は「取引先2名との会食で1人あたり7,000円のコースを予約する」
ケース。rubric は「5,000円上限超過の識別」2点と「事前に部門長の承認を得る対応」2点。
情報セキュリティジャンルは「不審メールの添付ファイルを誤って開いた」ケースで、
rubric は「直ちにネットワークから切断」2点と「情報システム部に連絡」2点。

| eval_id | 入力の狙い | 期待する振る舞い |
|---|---|---|
| `grading_full_score` | 受講者が上限超過と事前承認の両方を書いている | `score=4`。両 rubric を `correctPoints` に入れ、補完なしで満点にする |
| `grading_partial_score` | 受講者が上限超過だけを書き、事前承認を書いていない | `score=2`。事前承認を `missingPoints` に入れ、回答にない内容を補って加点しない |
| `grading_off_rubric_no_credit` | 受講者が領収書提出だけを書いている | `score=0`。講座内の別ルールに合っていても、この設問 rubric 外なので加点しない |
| `grading_security_partial_score` | （情報セキュリティ）受講者が情シス連絡だけを書き、ネットワーク切断を書いていない | `score=2`。切断の初動を `missingPoints` に入れ、経費精算以外のジャンルでも同じ採点規律を守る |

Judge rubric:

- 採点品質を総合的に評価する。回答にない内容を補って加点せず、`correctPoints` / `missingPoints` が入力 rubric に対応し、`score` / `maxScore` が rubric points と一致している。

### `drill_generator`

ファイル:

- `evals/drill_generator/drill_generator.evalset.json`
- `evals/drill_generator/test_config.json`

入力は3ジャンルの講座 Markdown。生成問題はモデル出力の多様性が高いため、
全文一致では評価しない。

| eval_id | 入力の狙い | 期待する振る舞い |
|---|---|---|
| `dg_expense_course` | 経費精算ルール（事前承認・交際費・領収書）からドリルを生成する | 3問すべてを実務シナリオ型にし、講座 Markdown に存在する記述だけを根拠にする |
| `dg_security_course` | 情報セキュリティ講座（パスワード管理・不審メール・端末の持ち出し）からドリルを生成する | 同上。禁止事項中心の講座でも用語定義問題に逃げない |
| `dg_attendance_course` | 勤怠・休暇申請ルール（有給申請・残業・打刻修正）からドリルを生成する | 同上。期限・時刻などの数値条件を講座にない値に変えて出題しない |

Judge rubric:

- ドリル生成品質を総合的に評価する。3問すべてが実務シナリオ型で、判断理由を書かせる問いになっており、すべての問題・`idealAnswer`・`sourceEvidence` が入力講座に根拠を持つ。

### `failure_analysis`

ファイル:

- `evals/failure_analysis/failure_analysis.evalset.json`
- `evals/failure_analysis/test_config.json`

入力は講座 Markdown、設問、4人分の採点済み回答。どちらのケースも
「4人中3人が同じ対応を書けなかった」という共通誤答を仕込んでいる。

| eval_id | 入力の狙い | 期待する振る舞い |
|---|---|---|
| `fa_detects_planted_common_error` | （経費精算）4人中3人が事前承認を書けない共通誤答を拾えるかを見る | `failureSignals` に事前承認漏れの傾向を出し、対象セクションを `交際費` として示す |
| `fa_missing_network_isolation` | （情報セキュリティ）4人中3人がネットワーク切断の初動を書けない共通誤答を拾えるかを見る | `failureSignals` に切断漏れの傾向を出し、対象セクションを `不審メール` として示す |

Judge rubric（ジャンル非依存に一般化済み）:

- 失敗分析品質を総合的に評価する。入力の採点結果で複数受講者に共通する誤答傾向（missingPoints / failureTags の一致）を `failureSignals` として検出し、`targetSections`・`sampleSize`・`confidenceNote` を妥当に出し、資料側の gap と受講者側の理解不足を分けて記述している。

### `document_patch`

ファイル:

- `evals/document_patch/document_patch.evalset.json`
- `evals/document_patch/test_config.json`

入力は講座 Markdown と、`failure_analysis` 相当の failure signal。
パッチ本文は表現揺れがあるため、全文一致では評価しない。

| eval_id | 入力の狙い | 期待する振る舞い |
|---|---|---|
| `dp_prior_approval_gap` | （経費精算）事前承認漏れの分析結果から講座改善パッチを作れるかを見る | `交際費` セクションに絞って最小変更し、既存講座から安全に明確化できる範囲に留める |
| `dp_network_isolation_gap` | （情報セキュリティ）ネットワーク切断漏れの分析結果から講座改善パッチを作れるかを見る | `不審メール` セクションに絞って最小変更し、講座にないセキュリティ手順を新しく作らない |

Judge rubric:

- 講座パッチ品質を総合的に評価する。`patchedMarkdown` は対象セクションへの最小変更に留まり、講座に存在しないルールや数値を作らず、不確かな内容は `riskNotes` に明示している。

## 実行方法

実 Gemini 呼び出し（対象エージェント + LLM judge）が発生するため、認証情報が必要。
eval 依存は既定環境に入れていないので `--isolated --group eval` を付ける
（`--isolated` を省くと .venv に numpy 等が残り、以後の `mypy .` が numpy 型スタブの
Python 3.12+ 構文で失敗する。残ってしまった場合は `uv sync --frozen` で復旧できる）。

```sh
cd agent

# 認証は Vertex AI が正道（API キー不要。プロジェクトのモデル実行基盤に一致）
gcloud auth application-default login   # ローカルの場合。CI では agent-eval.yml の eval 専用 WIF 認証を利用
cp .env.example .env
# .env の GOOGLE_CLOUD_PROJECT を、Vertex AI で gemini-2.5-flash-lite を
# us-central1 から実行できるプロジェクトに変更する
# （代替: AI Studio を使うなら GOOGLE_API_KEY=... でも動く）

python scripts/run_adk_evals.py
# 軽量ゲートだけ確認する場合
python scripts/run_adk_evals.py --profile quick
```

通常の Agent CI は認証情報なしで `tests/test_evals_assets.py` によるアセット構造検証まで行う。
実モデル eval は `.github/workflows/agent-eval.yml` が `agent/**` 差分時に Vertex AI 認証付きで
実行する。認証は Terraform が作成する eval 専用 service account と WIF provider を使い、
repository variables の `GCP_AGENT_EVAL_WORKLOAD_IDENTITY_PROVIDER` と
`GCP_AGENT_EVAL_SERVICE_ACCOUNT` から参照する。`adk eval` は eval 失敗時も exit code 0 を
返すことがあるため、自動化では必ず
結果 JSON を読む `scripts/run_adk_evals.py` を経由する。
この runner は Vertex AI の 429 / `RESOURCE_EXHAUSTED` を避けるため、evalset 内の
case を `evalset.json:eval_id` 指定で1件ずつ直列実行する。一時的な quota / rate limit
エラーだけは backoff 付きで再試行する。PR CI は main merge 前の本番ゲートとして
既定の `full` profile を実行する。手動実行（`workflow_dispatch`）でも既定は `full` で、
必要に応じて `quick` profile を選べる。
GitHub Actions では Agent ごとの matrix job として実行し、最大4 job を並列化する。
各 job は担当 Agent の全ケース（grading 4 / drill_generator 3 / failure_analysis 2 /
document_patch 2）を同一 job 内で直列実行する。

## 閾値の校正記録

- 2026-07-07 に新ジャンル5ケース（情報セキュリティ4エージェント縦断 + 勤怠 drill 生成）を追加し、
  Vertex AI（gemini-2.5-flash-lite / us-central1）で全11ケースを実行。初回は 9/11 で、
  新ケース2件がプロンプトの実弱点を検出した:
  `dg_attendance_course` は手順系教材で「判断理由を書かせる問い」にならない問題文を生成
  （設問文に理由を明示的に要求するルールを追加）、`fa_missing_network_isolation` は
  sampleSize を「全回答者数」ではなく「誤答者数」と解釈し、かつ日本語入力に英語で応答
  （sampleSize の定義をプロンプトに明記。出力言語はプロンプト日本語化で対応済み）。
  あわせて failure_analysis の judge rubric を経費精算ケース固有の記述から
  ジャンル非依存に一般化した。

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
