# failure_analysis_agent Agentic Workflow 化 詳細設計

- ステータス: ドラフト（レビュー待ち）
- 作成日: 2026-07-07
- 更新日: 2026-07-08
- 対象: `agent/knowledge_drill_agent/` の `failure_analysis_agent`
- 前提バージョン: google-adk 2.3.0（`agent/.venv` で API 挙動を確認済み）

## 1. 背景と目的

現行の `failure_analysis_agent` は `input_schema` / `output_schema` 付きの単一 `Agent` で、
1 回の LLM 呼び出しに以下をすべて担わせている。

- 採点結果からの反復失敗パターン抽出
- 誤答原因（学習者の理解不足）の分析 → `likelyCause`
- 教材文書の記述不備の特定 → `suspectedDocumentGap` / `targetSections`
- 定量的な根拠づけ → `sampleSize` / `severity` / `confidenceNote`
- ハルシネーション抑止ルールの遵守（社内ルール捏造禁止・根拠実在性・学習者非難禁止）

これを **「並列専門家分析 → critic による評価 → critic 評価のレビュー → 契約 JSON 整形」** の
Agentic Workflow に再構成する。狙いは次の 3 点。

1. **マルチエージェント協調**をアーキテクチャとして明示する（ハッカソン審査観点）
2. 現行プロンプトで「お願い」しているだけの品質ルールを、**批評エージェントと reviewer による検証ゲート**に昇格させる
3. backend / evals の既存の必須契約（`FailureAnalysisInput` → `FailureAnalysisOutput`）を壊さない  
   注: hackathon-feedback-loop spec で追加する optional `perspectives` は後方互換 field として扱う

## 2. 全体アーキテクチャ

```
failure_analysis_pipeline (SequentialAgent)
│
├── ① analyst_parallel (ParallelAgent)             … 3 観点でコンテキストを集める
│     ├── misconception_analyst     → state["misconception_findings"]
│     ├── document_gap_analyst      → state["doc_gap_findings"]
│     └── question_quality_analyst  → state["question_quality_findings"]
│
├── ② review_loop (LoopAgent, max_iterations=3)    … critic 評価と評価レビュー
│     ├── evidence_critic (LlmAgent)
│     │     └── analyst outputs を評価 → state["evidence_review"]
│     └── critic_reviewer (LlmAgent, tools=[exit_loop])
│           └── evidence_review をレビュー → state["critic_review"]
│               ├── approved: exit_loop
│               └── needs_revision: 次周の evidence_critic に差し戻し
│
└── ③ finalizer (LlmAgent, output_schema=FailureAnalysisOutput)
      └── analyst outputs + approved/latest evidence_review を契約 JSON に整形（最終レスポンス）
```

`signal_aggregator` / `draft_builder` / `signal_refiner` は置かない。
並列分析の結果を途中で FailureSignal 草案にせず、`evidence_critic` が raw findings を評価し、
`finalizer` が最終的に `FailureAnalysisOutput` へ整形する。

データフローは session state 経由。各エージェントは `output_key` で state に書き、
後続エージェントは instruction 内のプレースホルダ（例: `{evidence_review}`）で参照する
（ADK の instruction templating）。

入力の `FailureAnalysisInput` JSON はユーザーメッセージとして会話履歴に載るため、
①の各専門家はそこから直接読める。state への事前注入は不要。

## 3. 各エージェント仕様

共通: モデルは現行同様 `get_agent_settings().model`（`KNOWLEDGE_DRILL_AGENT_MODEL`）を
呼び出し時解決。プロンプトは `knowledge_drill_agent/prompts/failure_analysis/` 配下に新設。

### 3.1 misconception_analyst（誤解・つまずき分析）

| 項目 | 内容 |
|---|---|
| 責務 | 採点結果を横断し、学習者の誤解・知識不足・反復つまずきのパターンを抽出する |
| 入力 | ユーザーメッセージ（`FailureAnalysisInput` JSON） |
| output_key | `misconception_findings` |
| 出力形式 | 所見リスト（JSON テキスト）: `findingId` / `pattern` / `affectedLearners` / `questionIds` / `evidenceQuotes` / `likelyCause` |
| プロンプト要点 | missingPoints・failureTags の一致を優先。単発ミスより反復パターン。学習者名は evidence 集計にのみ使用 |

### 3.2 document_gap_analyst（教材ギャップ分析）

| 項目 | 内容 |
|---|---|
| 責務 | `courseMarkdown` を精査し、失点箇所に対応する記述の欠落・曖昧さを特定する |
| 入力 | 同上 |
| output_key | `doc_gap_findings` |
| 出力形式 | 所見リスト: `findingId` / `sectionHeading` / `gapDescription` / `relatedQuestionIds` / `supportingExcerpt` / `recommendedChange` |
| プロンプト要点 | courseMarkdown に実在するセクション見出しのみ `sectionHeading` に使う。文書にない社内ルール・事実の捏造禁止 |

### 3.3 question_quality_analyst（設問品質分析）

| 項目 | 内容 |
|---|---|
| 責務 | 誤答が教材ギャップではなく、設問・rubric・idealAnswer の曖昧さや誘導不足に起因していないかを分析する |
| 入力 | 同上 |
| output_key | `question_quality_findings` |
| 出力形式 | 所見リスト: `findingId` / `questionId` / `qualityIssue` / `rubricIssue` / `evidence` / `recommendedAction` |
| プロンプト要点 | 教材を直すべきケースと設問側を直すべきケースを分ける。設問側が主因なら document patch を強く推さない |

### 3.4 evidence_critic（所見評価）

現行プロンプトの Rules をチェックリスト化した批評専用エージェント。
**FailureSignal は作らない。raw findings を採用・棄却・注意点に分けて評価する。**

| 項目 | 内容 |
|---|---|
| 責務 | 3 analyst の findings を入力データと突合し、finalizer が使うべき評価コンテキストを作る |
| 参照 state | `{misconception_findings}` `{doc_gap_findings}` `{question_quality_findings}` `{critic_review}`（2 周目以降のみ） |
| output_key | `evidence_review` |
| 出力形式 | `{"acceptedFindings": [...], "rejectedFindings": [...], "finalizerGuidance": [...], "risks": [...], "revisionNotes": [...]}` |

チェックリスト（現行 `failure_analysis.md` の Rules 由来）:

1. 各 finding の evidence は供給された採点データ・回答に実在するか（引用捏造の検出）
2. sample size・失点者数・頻度表現は入力データと一致するか
3. `targetSections` / `sectionHeading` は courseMarkdown に実在する見出しか
4. courseMarkdown にない社内ルール・ポリシー・事実・義務を捏造していないか
5. 学習者を責める表現がないか
6. `likelyCause`（理解不足）、`suspectedDocumentGap`（文書不備）、設問品質問題が区別されているか
7. 単発ミスが教材ギャップとして過大評価されていないか
8. finalizer が採用すべき主因・補助要因・棄却理由が明確か

`critic_review.verdict == "needs_revision"` の次周では、reviewer の指摘を優先して
`evidence_review` を出し直す。raw findings 自体は書き換えない。

### 3.5 critic_reviewer（critic 評価レビュー）

`evidence_critic` の評価そのものをレビューする。**所見を直接修正しない。**
レビュー対象は `evidence_review` であり、approved なら `exit_loop` を呼ぶ。

| 項目 | 内容 |
|---|---|
| 責務 | evidence_critic の採用・棄却・finalizerGuidance が入力データと analyst outputs に基づいて妥当かを検証する |
| 参照 state | `{misconception_findings}` `{doc_gap_findings}` `{question_quality_findings}` `{evidence_review}` |
| output_key | `critic_review` |
| tools | `google.adk.tools.exit_loop`（`tool_context.actions.escalate = True` を立てる公式ツール。存在確認済み: `google/adk/tools/exit_loop_tool.py`） |
| 出力形式 | `{"verdict": "approved" \| "needs_revision", "issues": [...], "revisionInstructions": [...], "approvedFindingIds": [...], "riskNotes": [...]}` |
| プロンプト要点 | `approved` なら `exit_loop` を呼ぶ。`needs_revision` なら evidence_critic が次周で評価を直せるよう、問題点を短く具体的に返す |

ループ上限は `LoopAgent(max_iterations=3)`。
3 周しても approved にならない場合は、最新の `critic_review.approvedFindingIds` が非空なら
その finding だけを partial 採用する。`approvedFindingIds` が空なら finalizer は有効な
`FailureAnalysisOutput` を生成せず、backend の分析失敗フローに倒す。未承認 finding は採用しない。

### 3.6 finalizer（整形）

| 項目 | 内容 |
|---|---|
| 責務 | analyst outputs と approved/latest `evidence_review` を `FailureAnalysisOutput` に整形して最終レスポンスを出す |
| 参照 state | `{misconception_findings}` `{doc_gap_findings}` `{question_quality_findings}` `{evidence_review}` `{critic_review}` |
| output_schema | `FailureAnalysisOutput`（既存必須 field + optional `perspectives` + optional `reviewNotes`） |
| プロンプト要点 | `critic_review.approvedFindingIds` に含まれる finding だけを使う。棄却 findings と未承認 findings は failureSignals に入れない。内容の新規発明は禁止 |

`output_schema` はこのバージョンの ADK では最終出力にのみスキーマ強制される仕様
（`llm_agent.py:369` の NOTE で確認済み）なので、契約 JSON の保証は現行と同等。

## 4. コード変更点

### 4.1 agent パッケージ

```
agent/knowledge_drill_agent/
├── agent.py                     # create_failure_analysis_agent() の返り値を
│                                #   SequentialAgent パイプラインに差し替え
├── prompts/
│   ├── failure_analysis.md      # single mode 用に維持、または finalizer 用に縮退
│   └── failure_analysis/        # 新設
│       ├── misconception_analyst.md
│       ├── document_gap_analyst.md
│       ├── question_quality_analyst.md
│       ├── evidence_critic.md
│       ├── critic_reviewer.md
│       └── finalizer.md
```

- `create_failure_analysis_agent(model)` のシグネチャと返り値型は `BaseAgent` 互換なので
  呼び出し側（invoker / evals / root_agent）のコードは変わらない
- **ファクトリは毎回新規インスタンスを返す現行方針を維持する**こと。
  ADK ではエージェントインスタンスは単一親しか持てないため、モジュールレベルの
  `failure_analysis_agent`（root_agent の sub_agent 用）とファクトリ生成物を共有してはならない
- `root_agent` の `sub_agents` にはパイプラインをそのまま入れられる
  （`SequentialAgent` も `BaseAgent` なので AutoFlow の transfer 先になれる）
- `KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE=single` の撤退経路は維持する

### 4.2 backend（契約追加あり）

`backend/app/clients/adk_agent_invoker.py` は `run_async` のイベントストリームから
final response の text を**上書きで拾い続け、最後のものを採用する**実装
（`_run_once`, adk_agent_invoker.py:149-163）。SequentialAgent では各サブエージェントの
完了が final response になり得るが、最後に final を出すのは finalizer なので、
採用されるのは finalizer の契約 JSON。よって invoker のイベント処理は無変更で動く。

backend schema と timeline mapping は追加する。

- `FailureAnalysisResponse` に optional `reviewNotes` を追加する
- `reviewNotes` は `id`、`source`、`timelineStep`、`title`、`summary`、`evidence` を持つ
- Backend は `reviewNotes.id` ではなく `timelineStep` で `analysisTimeline` の step に振り分ける
- review note 由来 evidence は既存 evidence より前に置き、重複除外後に最大 3 件へ制限する

timeout は既存値で足りる前提にせず、local/adk smoke で計測する。
backend local default は 60 秒、production Terraform は 120 秒。足りない場合は
`KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS` または `terraform/locals.tf` の
`backend_agent_timeout_seconds` を明示的に引き上げる。

### 4.3 evals

- `agent/evals/failure_analysis/agent.py` は `create_failure_analysis_agent()` を
  そのまま使っているため無変更でパイプラインが評価対象になる
- `failure_analysis.evalset.json` / `test_config.json`（rubric ベースの最終出力評価）は
  そのまま回帰テストとして機能する
- 追加検討（任意・後続タスク）: critic reviewer が検出すべき欠陥を仕込んだ eval ケース
  （例: evidence_critic が根拠不足 finding を採用するケース）を追加し、レビュー効果を可視化する
- CI の adk eval 実行時間・API コストが増える。並列 matrix 実行は導入済みのため
  ジョブ全体のタイムアウト値のみ確認する

## 5. ガードレール

| リスク | 対策 |
|---|---|
| 検証ループの無限化 | `LoopAgent(max_iterations=3)` + `critic_reviewer` の `exit_loop` |
| 全体の実行時間超過 | 既存 `agent_timeout_seconds`（invoker の `asyncio.wait_for`）が全体に効く。値を引き上げ |
| LLM 呼び出し暴走 | Runner の `RunConfig.max_llm_calls` 既定値が上限として効く |
| 中間出力の形式崩れ | `EvidenceReviewOutput` / `CriticReviewOutput` の軽量 schema と契約テストで固定する。最終契約は finalizer の `output_schema` で担保 |
| 3 周しても不合格 | `approvedFindingIds` が非空ならその ID だけ partial 採用。空なら分析失敗。未承認 finding は採用しない |
| reviewer が critic の自己追認になる | reviewer prompt で「critic 出力ではなく入力データと analyst outputs を正とする」と明記する |

## 6. 縮退プラン（時間切れ時の保険）

工数が厳しい場合、①の parallel を省略して次の構成に縮退できる。
段階的に実装する場合もこの順で作ると常に動く状態を保てる。

1. **Step 1**: `signal_extractor`（現行プロンプトほぼ流用）→ `evidence_critic` → `critic_reviewer` → `finalizer`
   （critic 評価と評価レビューだけで「自己検証するエージェント」のストーリーは成立する）
2. **Step 2**: extractor を `analyst_parallel` に分割（フル構成）

ただしハッカソン提出で「並列 Agent」を明示するため、提出版の目標は Step 2 とする。

## 7. 実装タスク分解（目安）

1. プロンプト 6 本の新規作成（`prompts/failure_analysis/`）
2. `agent.py`: パイプライン組み立て関数の実装・`create_failure_analysis_agent` 差し替え
3. 契約テスト更新: `tests/test_analysis_patch_agent_contract.py` で workflow 構造、
   `output_key`、中間 schema、`approvedFindingIds`、finalizer の `output_schema` を確認する
4. backend schema / timeline mapping 追加（`reviewNotes`、`timelineStep`、最大 3 件 merge）
5. timeout 計測と必要時の `agent_timeout_seconds` 引き上げ（backend 設定 + Cloud Run 環境変数）
6. ローカル検証: `adk eval`（failure_analysis evalset）+ `backend/scripts/manual_adk_smoke.py`
7. （任意）critic reviewer 検証用 eval ケース追加

## 8. 未決事項（レビュー時に判断してほしい点）

1. **`failure_analysis.md`（現行プロンプト）の扱い**: single mode 用に残すか、finalizer 用に縮退するか
2. **タイムアウト具体値**: 現行値と実測レイテンシを見て決定
