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
3. `LoopAgent` は reviewer が `exit_loop` を呼ぶことで終了できる。次 iteration の agent は前回の reviewer 出力を session state から参照できる。
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
