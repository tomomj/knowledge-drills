# Research Notes

## DeepWiki 調査

### 対象

- `tomomj/knowledge-drills`
- `google/adk-python`

### 結果

`tomomj/knowledge-drills` は DeepWiki で未 index だったため、repository 固有の確認はローカルコードで行った。
DeepWiki では `google/adk-python` に対して、ADK の `SequentialAgent` / `ParallelAgent` / `LoopAgent` / `LlmAgent.output_key` / `output_schema` の使い方を確認した。

### 確認できた方針

1. Backend API が安定した JSON 契約を返したい場合、UI が ADK event stream を直接解釈するより、各 agent の中間出力を `output_key` で session state に保存し、最後の `finalizer` が `output_schema` 付きの最終 JSON にまとめる方が適している。
2. ADK event は実行中の細かい状態を出せる一方、UI が workflow 内部構造に強く依存し、response contract が不安定になりやすい。
3. `LoopAgent` は子 agent が `EventActions(escalate=True)` を返すことで終了できる。structured reviewer の出力を `output_key` で保存した後、LLM を呼ばない control agent が同じ保存済みレビューを検証して終了判定すれば、次 iteration または後続 finalizer へ安全に分岐できる。
4. `SequentialAgent` / `ParallelAgent` / `LoopAgent` は ADK 2.0 以降で Workflow engine への移行候補になっているが、現 repository は既にこれらの agent class を使っており、今回の hackathon 実装では既存パターンを維持する。

### 採用判断

- `evidence_critic` / `critic_reviewer` の中間結果は `output_key` で state に保存する。
- `finalizer` が `FailureAnalysisOutput` に optional な `reviewNotes` を入れて返す。
- Backend は `reviewNotes` を既存 `analysisTimeline` に変換する。
- Frontend は既存 `AnalysisTimeline` を使い、専用 workflow viewer や ADK event streaming は作らない。

## ローカルコード調査

### 現状

- `frontend/src/components/common/AnalysisTimeline.tsx` は `AnalysisTimelineItem[]` を表示できる。
- Drill Admin / Patch Review は既に `analysisTimeline` を表示している。
- Backend の `FailureAnalysisResponse` は `failureSignals` と `perspectives` のみを持つ。
- `AnalysisService._failure_pattern_evidence` は `perspectives` 先頭 3 件を timeline evidence に変換している。
- Agent の現行 composite は `ParallelAgent(3 lenses) -> synthesis_agent` であり、`evidence_critic` / `critic_reviewer` / loop は未実装。

### ギャップ

- UI の表示枠はあるが、critic / reviewer の結果を運ぶ契約がない。
- Agent workflow の深さが既存 `analysisTimeline` には現れない。
- `perspectives` に reviewer 情報を詰め込むと、3 観点分析とレビュー判断の意味が混ざる。

### 実装方針

- `perspectives` は analyst の観点別所見として維持する。
- `reviewNotes` を追加し、critic / reviewer / finalizer の監査用要約を分ける。
- Backend で review note を既存 5 step timeline に割り当てる。
- UI は大きく変えず、server 起動による挙動確認を重視する。

## 2026-07-10 DeepWiki / 公式 ADK 再調査

### 調査対象

- DeepWiki: [Workflow Agents](https://deepwiki.com/google/adk-docs/3.2-workflow-agents)
- DeepWiki: [Deep Search - Architecture and Sequential Pipeline](https://deepwiki.com/google/adk-samples/7.1-architecture-and-sequential-pipeline)
- DeepWiki: [Deep Search - RAG and Iterative Refinement](https://deepwiki.com/google/adk-samples/7.2-rag-and-iterative-refinement)
- DeepWiki: [ADK Python - Multi-Agent Orchestration](https://deepwiki.com/google/adk-python/3.5-session-and-state-management)
- 公式 ADK: [Loop template workflow agent](https://adk.dev/agents/workflow-agents/loop-agents/)
- 公式 sample source: [google/adk-samples deep-search agent.py](https://github.com/google/adk-samples/blob/441dde62de209e6f16b9856451f433656567359c/python/agents/deep-search/app/agent.py)
- repository が固定している `google-adk==2.3.0` のローカル実装

### 結論

「複数観点から情報を収集し、評価とレビューを反復し、不十分なら修正して次周へ進み、十分なら loop を終了して finalizer へ進む」という方針は、ADK の標準的な iterative refinement workflow と一致する。

ADK は workflow agent を、LLM が経路を自由選択する agent とは別の、コードで実行順を制御する deterministic な agent workflow と位置づけている。したがって、固定された `Parallel -> Loop -> Finalize` の構造であること自体は agentic workflow ではないことを意味しない。

### Deep Search sample との対応

Google の Deep Search sample は、次の構成を採用している。

1. 情報収集結果を state に保存する
2. structured output を返す evaluator が品質を評価し、その結果を state に保存する
3. LLM を呼ばない custom `EscalationChecker` が保存済み評価を読む
4. 評価が pass なら `EventActions(escalate=True)` により loop を終了する
5. fail なら追加調査・改善を実行し、次 iteration で再評価する
6. loop 終了後に composer が最終結果を生成する

これは Knowledge Drills の `analyst findings -> evidence review -> critic review -> finalizer` とほぼ同型である。現行実装との差は、structured reviewer 出力を保存した後に終了判定を行う control checker が欠けていることである。

### `exit_loop` と state 保存

公式の LoopAgent 文書では、品質判定 agent と、必要に応じて `exit_loop` を呼ぶ refiner/exiter agent が分離されている。固定中の ADK 2.3.0 では組み込み `exit_loop` が `escalate=True` と `skip_summarization=True` を同時に設定し、`output_key` は最終 text response から state を更新する。

このため、1つの reviewer に「structured review の保存」と「text response を作らず即時終了」の両方を持たせるより、reviewer の出力保存後に deterministic checker が終了判定する方が、公式 Deep Search sample と整合し、state 消失を避けられる。

### 要件への反映方針

- 早期終了は特定 tool の利用ではなく、「保存済みの最新レビューが承認なら追加 cycle を実行しない」という外部から検証可能な挙動として定義する
- 修正要求なら、反復上限までは前回の問題点と修正指示を次の根拠評価へ渡す
- 反復上限では、有効な承認対象があれば部分採用し、明示的な空選択なら patch 見送りとする。field 欠落や追跡不能な review だけを明示的な分析失敗とする
- 承認対象の一意性、採用候補への包含、採用・棄却間の排他性を検証可能な要件にする
- finalizer は保存済みの承認対象だけを根拠にし、中間出力を最終応答として返さない
- `LoopAgent`、custom agent、`exit_loop`、graph Workflow の選択は design の責務とし、requirements では特定実装を固定しない

### ADK 2.0 Workflow について

ADK 2.0 以降は graph-based Workflow が template workflow agents の後継として案内されており、conditional route と cycle で同じ処理を表現できる。ただし、今回の要件を満たすために即時移行は必須ではない。現行 ADK 2.3.0 と既存コードに対する最小変更は、Deep Search sample と同様に structured reviewer と deterministic control checker を分離することである。
