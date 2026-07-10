# Technical Design Document

## Overview

**Purpose**: Failure Analysis Review Loop は、誤答分析 Agent を「並列分析だけ」から「並列分析 + 根拠評価 + 評価レビュー + 最終化」に拡張し、review 結果を既存タイムライン UI に表示する。

**Users**: 講座オーナーと審査員は Drill Admin / Patch Review で、Failure Signal がどの観点から出て、どの根拠評価を通って patch に使われたかを確認する。

**Impact**: Agent package の workflow / schema / prompt、Backend schema と `AnalysisService` の timeline 変換、Frontend の timeline 表示テストを変更する。新しいインフラ、event streaming、専用 viewer は導入しない。

### Goals

- `analyst_parallel -> review_loop -> approved_findings_gate -> finalizer` の agent workflow を実装する
- `reviewNotes` を optional field として追加し、既存 response contract を壊さない
- review 結果を既存 `analysisTimeline` に保存し、Drill Admin / Patch Review に表示する
- server 起動による demo smoke で挙動確認できる状態にする

### Non-Goals

- ADK event stream を UI に直接流す
- SSE / WebSocket / background worker を導入する
- Chain-of-thought や prompt 本文を保存・表示する
- 既存 5 step timeline を workflow graph UI に置き換える
- patch review 専用 agent を追加する

## Boundary Commitments

### This Spec Owns

- `failure_analysis_agent` の review loop workflow
- `FailureAnalysisOutput.reviewNotes` / Backend `FailureAnalysisResponse.reviewNotes`
- `AnalysisService` による review note -> `AnalysisTimelineItem.evidence` 変換
- review loop の prompt、sample output、contract tests
- server smoke で確認する手順と観測項目

### Out of Boundary

- Course / Drill / Patch の永続化モデル全体の再設計
- 受講者向け画面・API への管理情報露出
- 認証・owner check・Firestore infrastructure
- metrics API / Before After 表示の仕様変更

### Allowed Dependencies

- `hackathon-feedback-loop` spec で追加済みの `analysisTimeline`、`perspectives`、`AnalysisTimeline` component
- `AgentRuntimeClient` / `AdkAgentInvoker` / `LocalAgentInvoker`
- Google ADK の `SequentialAgent` / `ParallelAgent` / `LoopAgent` / `BaseAgent` / `output_key` / `EventActions`

### Revalidation Triggers

- `FailureAnalysisOutput.failureSignals` の必須契約を変える場合
- `AnalysisTimelineItem` の形を変える場合
- ADK event streaming を API contract に入れる場合
- `KNOWLEDGE_DRILL_AGENT_ANALYSIS_MODE` の意味を変える場合

## Architecture

### Existing Architecture Analysis

- 現行の composed failure analysis は `ParallelAgent(3 lenses) -> synthesis_agent` で、`synthesis_agent` だけが `FailureAnalysisOutput` を返す。
- Backend は `FailureAnalysisResponse.perspectives` を `detect_failure_patterns` の evidence に変換している。
- Frontend は既存 `AnalysisTimeline` component を Drill Admin / Patch Review で表示している。
- したがって UI を増やすより、Agent 最終 JSON と Backend timeline 変換を拡張するのが最小変更になる。

### Architecture Pattern & Boundary Map

```mermaid
graph TB
    subgraph AgentPackage
        Input[FailureAnalysisInput]
        Parallel[analyst_parallel / ParallelAgent]
        Misconception[misconception_analyst]
        DocGap[document_gap_analyst]
        QuestionQuality[question_quality_analyst]
        Loop[review_loop / LoopAgent max_iterations=3]
        Critic[evidence_critic]
        Reviewer[critic_reviewer / structured output]
        ReviewGate[review_gate / deterministic BaseAgent]
        ApprovedGate[approved_findings_gate / deterministic BaseAgent]
        Finalizer[finalizer / output_schema=FailureAnalysisOutput]
    end

    subgraph Backend
        Runtime[AgentRuntimeClient]
        Schemas[FailureAnalysisResponse + reviewNotes]
        AnalysisSvc[AnalysisService timeline mapper]
        DrillRun[DrillRun.analysisTimeline]
        Patch[DocumentPatch.analysisTimeline]
    end

    subgraph Frontend
        DrillAdmin[DrillAdminPage polling]
        PatchReview[PatchReviewPage]
        Timeline[AnalysisTimeline]
    end

    Input --> Parallel
    Parallel --> Misconception
    Parallel --> DocGap
    Parallel --> QuestionQuality
    Misconception --> Loop
    DocGap --> Loop
    QuestionQuality --> Loop
    Loop --> Critic
    Critic --> Reviewer
    Reviewer --> ReviewGate
    ReviewGate -->|needs_revision or invalid| Critic
    ReviewGate -->|valid approved / escalate| ApprovedGate
    Loop -->|max iterations| ApprovedGate
    ApprovedGate -->|valid full or partial selection| Finalizer
    ApprovedGate -->|valid explicit zero selection| Finalizer
    ApprovedGate -->|malformed or untraceable review| Failure[explicit analysis failure]
    Finalizer --> Runtime
    Runtime --> Schemas
    Schemas --> AnalysisSvc
    AnalysisSvc --> DrillRun
    AnalysisSvc --> Patch
    DrillRun --> DrillAdmin
    Patch --> PatchReview
    DrillAdmin --> Timeline
    PatchReview --> Timeline
```

**Architecture Integration**:
- Selected pattern: 公式 Deep Search sample と同様に、structured reviewer と deterministic control agent を分離する。ADK session state を workflow 内の中間データ bus とし、finalizer が stable JSON を返す
- Domain boundaries: Agent は分析結果と review note を返す。Backend は timeline 表示形式に変換する。Frontend は timeline を表示するだけにする
- Existing patterns preserved: synchronous analyze API、camelCase Pydantic schema、factory based agent creation、existing polling UI
- New components rationale: `reviewNotes` は `perspectives` と review 判断を混ぜないために追加する。Backend の step 振り分けは `id` ではなく `timelineStep` で固定する

### Technology Stack

| Layer | Choice / Version | Role in Feature | Notes |
|-------|------------------|-----------------|-------|
| Agent | Google ADK（既存） | Parallel / Loop / Sequential orchestration | 新規依存なし |
| Backend | FastAPI + Pydantic v2（既存） | response validation と timeline mapping | optional field 追加のみ |
| Frontend | React + TypeScript（既存） | 既存 timeline 表示 | 新規依存なし |
| Runtime | local / adk mode（既存） | local smoke と実 agent 実行 | single mode fallback 維持 |

## File Structure Plan

### Modified Files

- `agent/knowledge_drill_agent/schemas.py` — `AnalysisReviewNote`、必要なら中間出力用 model、`FailureAnalysisOutput.review_notes`
- `agent/knowledge_drill_agent/agent.py` — review loop 付き composed agent factory
- `agent/knowledge_drill_agent/failure_analysis_workflow.py` — 保存済み review の検証、loop 終了判定、finalizer 向け承認対象の確定
- `agent/knowledge_drill_agent/prompts/*.md` — analyst / evidence critic / critic reviewer / finalizer prompt
- `agent/knowledge_drill_agent/sample_outputs/failure_analysis.json` — `reviewNotes` を含む sample
- `agent/tests/test_analysis_patch_agent_contract.py` — workflow 構造と schema 契約
- `agent/tests/test_failure_analysis_workflow.py` — ADK Runner 上の早期終了、継続、上限、fail-closed の挙動
- `backend/app/schemas.py` — `FailureAnalysisResponse.review_notes`
- `backend/app/services/analysis_service.py` — review note から timeline evidence への変換
- `backend/app/clients/local_agent_invoker.py` — local smoke 用の optional `reviewNotes`
- `backend/tests/test_schemas.py` / `backend/tests/test_analysis_service.py` / `backend/tests/test_agent_contract_compatibility.py` — schema 互換と timeline mapping
- `frontend/src/api/types.ts` — API contract に raw failure analysis 型を持つ場合のみ `reviewNotes` を追加
- `frontend/src/components/common/AnalysisTimeline.test.tsx` / page tests — review note 由来の evidence 表示

### New Files

- `agent/knowledge_drill_agent/prompts/failure_analysis_evidence_critic.md`
- `agent/knowledge_drill_agent/prompts/failure_analysis_critic_reviewer.md`
- `agent/knowledge_drill_agent/prompts/failure_analysis_finalizer.md`

## System Flows

### Failure analysis review loop

```mermaid
sequenceDiagram
    participant B as Backend
    participant P as analyst_parallel
    participant C as evidence_critic
    participant R as critic_reviewer
    participant G as review_gate
    participant A as approved_findings_gate
    participant F as finalizer

    B->>P: FailureAnalysisInput
    par 3 analysts
        P->>P: misconception_findings
        P->>P: doc_gap_findings
        P->>P: question_quality_findings
    end
    loop max 3
        P->>C: analyst outputs + previous reviewer notes
        C-->>R: evidence_review
        R-->>G: critic_review saved in state
        alt valid approved
            G-->>A: EventActions(escalate=True)
        else needs_revision or invalid reference
            G-->>C: continue next cycle
        end
    end
    A->>A: validate and select approved findings
    alt valid full or partial selection
        A-->>F: approved_findings + termination reason
    else valid explicit zero selection
        A-->>F: empty approved_findings + patch skip reason
    else malformed or untraceable review
        A-->>B: explicit analysis failure
    end
    F-->>B: FailureAnalysisOutput + perspectives + reviewNotes
```

### Timeline mapping

```mermaid
graph LR
    Perspectives[perspectives] --> Detect[detect_failure_patterns evidence]
    EvidenceReview[evidence_critic review note] --> Match[match_course_evidence evidence]
    CriticReview[critic_reviewer review note] --> Strategy[decide_patch_strategy evidence]
    FinalizerNote[finalizer review note] --> Strategy
```

## Requirements Traceability

| Requirement | Summary | Components | Interfaces | Flows |
|-------------|---------|------------|------------|-------|
| 1.1-1.15 | review loop workflow | agent.py, failure_analysis_workflow.py, prompts | ADK state / output_key / EventActions | Failure analysis review loop |
| 2.1-2.7 | stable response contract | agent schemas, backend schemas | FailureAnalysisOutput / FailureAnalysisResponse | Timeline mapping |
| 3.1-3.8 | timeline mapping | AnalysisService | AnalysisTimelineItem | Timeline mapping |
| 4.1-4.6 | existing UI display and smoke | DrillAdminPage, PatchReviewPage, AnalysisTimeline | analysisTimeline | Timeline mapping |
| 5.1-5.6 | regression and fallback | config, tests, local invoker | analysis mode env | Failure analysis review loop |

## Components and Interfaces

| Component | Domain/Layer | Intent | Req Coverage | Key Dependencies | Contracts |
|-----------|--------------|--------|--------------|------------------|-----------|
| failure analysis review workflow | agent | 並列分析結果を critic/reviewer loop と deterministic gate で検証して finalizer に渡す | 1, 5 | Google ADK | Service, State |
| review notes schema | agent/backend | review 判断を stable JSON で運ぶ | 2, 3 | Pydantic | API |
| timeline mapper | backend service | review notes を既存 5 step timeline に変換する | 3 | AnalysisService | State |
| AnalysisTimeline display | frontend component | timeline evidence を表示する | 4 | props only | State |

### Agent Package

#### failure analysis review workflow

| Field | Detail |
|-------|--------|
| Intent | analyst outputs を根拠評価とレビューで絞り、最終 `FailureAnalysisOutput` を作る |
| Requirements | 1.1-1.15, 5.1-5.2 |

**Responsibilities & Constraints**
- analyst agent は raw findings を `output_key` に保存する
- `evidence_critic` は failure signal を直接確定せず、`EvidenceReviewOutput` として採用/棄却/リスク/finalizer guidance を返す
- `critic_reviewer` は critic の評価品質をレビューし、structured `CriticReviewOutput` を state に保存する。tool による loop 制御は担当しない
- `review_gate` は保存済み `EvidenceReviewOutput` と `CriticReviewOutput` を決定論的に検証し、有効な承認だけで `EventActions(escalate=True)` を返す
- `approved_findings_gate` は loop 終了後に最新 state を再検証し、finalizer が参照できる承認済み finding だけを `approved_findings` に保存する
- `finalizer` は `approved_findings` を Failure Signal の唯一の finding source として最終 JSON を一度だけ返す
- review loop が max iteration に到達して `verdict=needs_revision` のままでも、`approvedFindingIds` が非空ならその finding だけを partial 採用する。構造的に有効なレビューで `approvedFindingIds` が空なら、未承認 finding を採用せず、空の `failureSignals` と見送り理由を返す
- finalizer 以外の中間出力は backend API contract に直接出さない

**State Keys**

| Key | Producer | Consumer |
|-----|----------|----------|
| `misconception_findings` | misconception analyst | evidence_critic, finalizer（perspectives / reviewNotes の要約だけ） |
| `doc_gap_findings` | document gap analyst | evidence_critic, finalizer（perspectives / reviewNotes の要約だけ） |
| `question_quality_findings` | question quality analyst | evidence_critic, finalizer（perspectives / reviewNotes の要約だけ） |
| `evidence_review` | evidence_critic | critic_reviewer, finalizer, next evidence_critic |
| `critic_review` | critic_reviewer | evidence_critic, review_gate, approved_findings_gate, finalizer |
| `approved_findings` | approved_findings_gate | finalizer |
| `review_termination_reason` | approved_findings_gate | finalizer |

**Intermediate Output Contracts**

```python
class ReviewedFinding(AgentModel):
    finding_id: str
    source: Literal[
        "misconception_analyst",
        "document_gap_analyst",
        "question_quality_analyst",
    ]
    summary: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)

class EvidenceReviewOutput(AgentModel):
    accepted_findings: list[ReviewedFinding] = Field(default_factory=list)
    rejected_findings: list[ReviewedFinding] = Field(default_factory=list)
    finalizer_guidance: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    revision_notes: list[str] = Field(default_factory=list)

class CriticReviewOutput(AgentModel):
    verdict: Literal["approved", "needs_revision"]
    issues: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)
    approved_finding_ids: list[str]
    risk_notes: list[str] = Field(default_factory=list)
```

- `evidence_critic` は前回の `critic_review.revisionInstructions` と `issues` を読み、`revision_notes` に何を修正したかを残す
- `critic_reviewer` は review を state に保存するだけで、終了判定を prompt や tool call に委ねない
- `review_gate` は accepted / rejected の ID がそれぞれ一意かつ相互排他で、全 finding の ID・source・evidence が非空であり、`verdict=approved`、`approved_finding_ids` が一意かつ採用候補の ID に包含される場合に loop を終了する。空の `approved_finding_ids` は field が明示されている場合に限り、見送り判断として許可する
- `approved_finding_ids` field 自体は必須とし、省略された review を暗黙の空選択に補完しない
- `verdict=needs_revision`、重複 ID、不明 ID、採用・棄却間の矛盾、accepted / rejected finding の追跡情報不足は承認として扱わず、反復上限までは次 cycle を実行する
- `approved_finding_ids` は finalizer が採用してよい finding の allowlist であり、`verdict` の自由文や `summary` から推測してはならない
- `approved_findings_gate` は max iteration 到達時に `verdict=needs_revision` でも、cycle 全体に重複・不明参照・矛盾・追跡情報不足がなく、有効な `approved_finding_ids` が非空で、かつ `issues`、`revision_instructions`、`risk_notes` がそれぞれ非空・非空白なら、その ID だけを部分採用し、`review_termination_reason=max_iterations_partial` を保存する
- `approved_finding_ids` に有効 ID と不明・重複・矛盾 ID が混在する場合は valid ID だけを救済せず、選択全体を無効として fail closed にする
- 構造的に有効だが承認対象がない場合、`approved_findings_gate` は空の `approved_findings` と `approved_no_findings` または `max_iterations_no_findings` を保存し、finalizer の callback が `failureSignals=[]` と見送り `reviewNote` を保証する
- 重複、不明参照、採用・棄却間の矛盾、追跡情報不足などレビュー構造が不正な場合だけ、`FailureAnalysisApprovalError` を送出して finalizer を実行しない
- 部分採用時は finalizer の `after_model_callback` がモデル出力を schema 検証したうえで、最新 `issues`、`revision_instructions`、`risk_notes` を evidence に持つ固定 ID の監査 `reviewNote` を決定論的に追加する。モデルが `reviewNotes=[]` を返してもこの note は必ず最終 JSON に含まれる
- finalizer は raw analyst state を `perspectives` と表示用 `reviewNotes` の要約にだけ使用でき、Failure Signal の finding source には `approved_findings` だけを使用する

**Control Agent Contracts**

```python
class ReviewLoopGate(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]: ...

class ApprovedFindingsGate(BaseAgent):
    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]: ...

class FailureAnalysisApprovalError(RuntimeError): ...

def ensure_partial_review_note(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse | None: ...
```

- state 値は Pydantic model、dict、JSON string のいずれでも同じ schema へ正規化する
- `ReviewLoopGate` は state を変更せず、valid approval のときだけ `EventActions(escalate=True)` を持つ event を返す
- `ApprovedFindingsGate` は validation 済み finding と終了理由を `EventActions.state_delta` で保存する
- `ensure_partial_review_note` は `review_termination_reason=max_iterations_partial` の監査 note と、承認対象ゼロ時の `failureSignals=[]` / 見送り note を、`FailureAnalysisOutput` の camelCase JSON 契約を維持したまま決定論的に保証する
- control agent は LLM を呼ばず、レビュー自由文から承認状態や ID を推測しない

### Backend

#### review notes schema

```python
class AnalysisReviewSource(str, Enum):
    EVIDENCE_CRITIC = "evidence_critic"
    CRITIC_REVIEWER = "critic_reviewer"
    FINALIZER = "finalizer"

class AnalysisTimelineStepId(str, Enum):
    DETECT_FAILURE_PATTERNS = "detect_failure_patterns"
    MATCH_COURSE_EVIDENCE = "match_course_evidence"
    DECIDE_PATCH_STRATEGY = "decide_patch_strategy"

class AnalysisReviewNote(ApiModel):
    id: str
    source: AnalysisReviewSource
    timeline_step: AnalysisTimelineStepId
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)

class FailureAnalysisResponse(ApiModel):
    failure_signals: list[FailureSignal]
    perspectives: list[AnalysisPerspective] = Field(default_factory=list)
    review_notes: list[AnalysisReviewNote] = Field(default_factory=list)
```

**Compatibility**
- `reviewNotes` is optional and defaults to `[]`
- existing sample / local responses without `reviewNotes` remain valid
- frontend does not need to consume raw `FailureAnalysisResponse` unless a debug API is added
- `id` はログの安定識別子であり、Backend の step mapping には使わない
- `timelineStep` は `AnalysisTimelineItem.id` と同じ文字列を使い、Backend はこの field だけで振り分ける

#### timeline mapper

| Source | Timeline step | Evidence format |
|--------|---------------|-----------------|
| `perspectives` | `detect_failure_patterns` | `{title}: {summary}` |
| `reviewNotes` with `timelineStep=match_course_evidence` | `match_course_evidence` | `{title}: {summary}` + first evidence |
| `reviewNotes` with `timelineStep=decide_patch_strategy` | `decide_patch_strategy` | `{title}: {summary}` + first evidence |
| `reviewNotes` with `timelineStep=detect_failure_patterns` | `detect_failure_patterns` | `{title}: {summary}` + first evidence |

**Merge Order**

Backend は各 step の evidence を次の順で作る。

1. review note 由来 evidence を `timelineStep` ごとに抽出し、入力順を維持して先頭に置く
2. 既存 evidence を後ろに追加する
   - `detect_failure_patterns`: perspectives 由来 evidence、fallback として failure signal title
   - `match_course_evidence`: target section
   - `decide_patch_strategy`: recommended change
3. 空文字と重複を除外する
4. 各 step 最大 3 件に切る

この順序により、review note が存在する場合は UI の 3 件制限で reviewer 判断が隠れない。review note が存在しない場合は既存 evidence の順序と内容を維持する。

#### Timeout Budget

- backend local default は `KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS=60` 秒相当。
- production Terraform の backend Cloud Run env は現状 `backend_agent_timeout_seconds = "120"`。
- review loop は LLM call 数が増えるため、実装時の local/adk smoke で所要時間を計測する。
- 既存値で足りない場合は、手動 smoke では `KNOWLEDGE_DRILLS_AGENT_TIMEOUT_SECONDS` を明示的に上げる。production 反映が必要なら `terraform/locals.tf` の `backend_agent_timeout_seconds` 変更を同じ PR に含める。

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| review loop が出力を不安定にする | patch 生成失敗 | finalizer のみ `output_schema`、中間は state に閉じる |
| UI に情報を出しすぎる | demo で読みにくい | 既存 timeline に要約と最大 3 evidence で表示 |
| ADK loop が長くなる | latency 増加・timeout | `max_iterations=3`、timeout smoke、single mode fallback |
| reviewer が approve しない | 不要な patch または final output 停止 | `approvedFindingIds` と監査情報が有効なら部分採用し、承認対象ゼロなら空の Failure Signal と見送り note を返す。構造不正時だけ分析失敗とする |
| reviewer の structured output と loop 終了 tool が競合する | review state が欠落し、誤った分岐になる | reviewer は state 保存に限定し、後続の deterministic `ReviewLoopGate` が終了判定する |
| 不明・重複 finding ID が承認される | 未検証 finding が Failure Signal に混入する | loop 内と finalizer 前の二段階で ID 集合を検証し、fail closed にする |
