# 手動スモーク — real-agent-invocation

## 目的

実 Gemini 接続で、ドリル生成 → 採点 → 失敗分析 → ドキュメントパッチ提案の4操作が1周成功することを確認する。

## 実行前提

- `KNOWLEDGE_DRILLS_AGENT_MODE=adk`
- AI Studio の場合: `GOOGLE_API_KEY` を設定する
- Vertex AI の場合: `GOOGLE_GENAI_USE_VERTEXAI=TRUE`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` を設定する
- 任意: `KNOWLEDGE_DRILL_AGENT_MODEL` でモデルを指定する（未指定時は agent パッケージ既定）

## 実行手順

```sh
cd backend
export KNOWLEDGE_DRILLS_AGENT_MODE=adk
export GOOGLE_API_KEY=... # または Vertex AI 用 env 一式
uv run --frozen python -m scripts.manual_adk_smoke \
  --output ../.kiro/specs/real-agent-invocation/manual-smoke-result.json
```

成功時は `manual-smoke-result.json` に4操作の要約とレスポンス JSON が保存される。

## 成功判定

- `generateDrill.questionCount` が `3`
- `gradeAnswer.questionId` が生成された先頭設問 ID と一致する
- `analyzeFailures.failureSignalCount` が `1` 以上
- `proposeDocumentPatch.patchSummary` が空でない

## 実行結果

- 2026-07-06: Google Cloud ADC + Vertex AI モードで local backend server を起動し、API 経由で4操作1周に成功した。
  - Server: `http://127.0.0.1:8010`
  - Project: `technology-strategy-gen-ai`
  - Location: `asia-northeast1`
  - Result: `manual-smoke-result.json`
  - Flow: health 200 → course create 201 → drill generation 201 → learner drill get 200 → answer grading 201 → failure analysis + document patch proposal 200 → patch get 200
