# ハッカソン向け改善ループ機能 詳細設計

Status: Draft v0.2  
Date: 2026-07-07  
Scope: 出題観点入力、根拠付きドリル生成、分析 Agent 実行タイムライン、改善証拠の表示、ハッカソン戦略、マルチエージェント構成方針

## 1. 目的

Knowledge Drills の勝ち筋を、細かい問題編集機能ではなく次の 1 本の体験に絞る。

```text
教材 Markdown
  -> 出題したい観点
  -> AI が根拠付きドリルを生成
  -> 回答を収集
  -> 分析 Agent が誤答傾向と教材ギャップを特定
  -> Markdown patch を提案
  -> オーナーが apply
  -> 改善効果をデータで確認
```

この設計の主眼は、審査員に「AI が問題を作った」ではなく
「受講者のつまずきをテレメトリとして、教材が改善ループに入った」と伝えることである。

## 2. 方針

### 2.1 やること

- Course Editor に任意の `出題したい観点` を追加する
- Drill generation input にその観点を渡す
- Agent は観点を優先するが、教材 Markdown に根拠がない内容は出題しない
- 生成された `sourceEvidence.excerpt` が教材 Markdown に実在することを backend で検証する
- 分析中の進捗を Drill Admin にタイムライン表示する
- 分析後の判断ログを Patch Review に保存表示する

### 2.2 やらないこと

- ユーザーによる質問文の直接入力
- 生成済み設問の個別編集
- 1 問だけ再生成
- 問題バンク
- LMS 連携
- 複雑な権限・通知
- Chain-of-thought の表示

分析タイムラインで表示するのは思考過程ではなく、観測値、根拠、判断結果である。

## 3. UX 設計

### 3.1 Course Editor

教材 Markdown の下に任意入力欄を追加する。

Label:

```text
出題したい観点
```

Placeholder:

```text
例: 例外条件の判断、上限超過時の承認手順、問い合わせの振り分け
```

Hint:

```text
AI が問題を作るときに優先する観点です。教材に根拠がない内容は出題しません。
```

入力制約:

- optional
- trim 後に空なら `null`
- 最大 500 文字
- Markdown 本文とは別管理

表示上の扱い:

- 主要体験は「教材を貼る -> 保存 -> ドリル生成」のまま維持する
- 観点欄は補助入力であり、質問文作成欄に見せない
- 観点が未入力でも既存通りドリル生成できる

### 3.2 Drill Admin

上部のメタ情報に、生成時に使った観点を表示する。

```text
出題観点: 例外条件の判断
```

分析実行中は、回答数カードの下に `分析 Agent の実行状況` を表示する。

表示ステップ例:

1. 回答データを収集
2. つまずき箇所を特定
3. 教材の根拠を照合
4. 改善方針を判断
5. 修正案を作成

各ステップには `pending` / `running` / `completed` / `failed` / `skipped` の状態を持たせる。
本文は 1 行要約と、必要なら evidence を 1 から 3 件表示する。

### 3.3 Patch Review

Failure Signal の前に `分析 Agent の判断ログ` を表示する。

例:

```text
回答データを収集
4 件の採点済み回答を確認。平均点は 2.1 / 4.0。

つまずき箇所を特定
q2 で 3 / 4 人が「事前承認」に触れていない。

教材の根拠を照合
## 交際費 の超過時手続きが 1 文のみで、例がない。

改善方針を判断
数値上限の理解ではなく、超過時の行動手順が不足している。

修正案を作成
既存ルールを変えず、上限超過時の事前承認例を 1 つ追記。
```

この UI は「Agent が何を見て、何を根拠に patch を出したか」を見せるためのもの。
長文の推論ログやプロンプト本文は表示しない。

## 4. データモデル

### 4.1 Course

`drill_focus` を追加する。

```python
class Course(ApiModel):
    ...
    drill_focus: str | None = None
```

API alias は `drillFocus`。

対象 schema:

- `Course`
- `CourseCreateRequest`
- `CourseUpdateRequest`
- `CourseDetailResponse`
- `CourseRevision`

`CourseSummary` には含めない。講座一覧では不要で、一覧の視認性を落とすため。

Version ルール:

- `title` / `markdown` / `drillFocus` のいずれかを更新したら `Course.version` を 1 増やす
- `CourseRevision` に `drillFocus` を保存し、どの観点でその版の教材が管理されていたか追跡する

Validation:

- `drillFocus` は optional
- trim 後に空文字なら `None`
- 最大 500 文字

### 4.2 DrillRun

生成時点の観点を snapshot として保存する。

```python
class DrillRun(ApiModel):
    ...
    drill_focus: str | None = None
    analysis_timeline: list[AnalysisTimelineItem] = Field(default_factory=list)
```

理由:

- Course の観点が後から変わっても、過去 drill が何を意図して生成されたかを保持する
- Drill Admin で生成時の観点を表示できる
- 分析中のタイムラインを Drill Admin で polling 表示できる

### 4.3 DocumentPatch

分析完了時点のタイムラインを patch にコピーする。

```python
class DocumentPatch(ApiModel):
    ...
    analysis_timeline: list[AnalysisTimelineItem] = Field(default_factory=list)
```

理由:

- Patch Review で、後からでも Agent の判断ログを確認できる
- DrillRun の分析状態が変わっても、patch 提案時の根拠を監査できる

### 4.4 AnalysisTimelineItem

```python
class AnalysisStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AnalysisTimelineItem(ApiModel):
    id: str
    title: str
    status: AnalysisStepStatus
    summary: str
    evidence: list[str] = Field(default_factory=list)
    completed_at: str | None = None
```

`id` は固定値にする。

- `collect_answers`
- `detect_failure_patterns`
- `match_course_evidence`
- `decide_patch_strategy`
- `create_patch`

`summary` と `evidence` は Chain-of-thought ではなく、画面に出せる監査ログとして生成・保存する。

### 4.5 DrillScoreSummary

Drill Admin で「なぜ分析が必要なのか」を押下前に伝えるため、採点済み回答の集計を owner-only で返す。

```python
class QuestionScoreSummary(ApiModel):
    question_id: str
    prompt: str
    graded_answer_count: int
    average_score: float | None = None
    max_score: float
    common_missing_points: list[str] = Field(default_factory=list)
    failure_tags: list[str] = Field(default_factory=list)


class DrillScoreSummary(ApiModel):
    graded_answer_count: int
    average_score: float | None = None
    max_score: float
    questions: list[QuestionScoreSummary] = Field(default_factory=list)
```

表示位置:

- Drill Admin: 現在の平均点、採点済み回答数、設問ごとの平均点を表示する
- Analyze 実行中: `analysisTimeline` の `collect_answers` に同じ集計の要約を残す
- Patch Review: patch 判断に使ったサンプル数と failure signal を表示する
- Course Editor / Course History: 改善後の Before / After 比較を表示する

重要なのは、Drill Admin では「現時点の状態」を見せ、Before / After は教材更新後に Course 側で見せること。Drill Admin に改善比較まで詰め込むと、分析前の判断画面として重くなる。

## 5. API 設計

### 5.1 Course create/update

Request:

```json
{
  "title": "経費精算の判断基準",
  "markdown": "# 経費精算の判断基準\n...",
  "drillFocus": "上限超過時の承認判断"
}
```

Response:

```json
{
  "id": "course-1",
  "title": "経費精算の判断基準",
  "markdown": "# 経費精算の判断基準\n...",
  "drillFocus": "上限超過時の承認判断",
  "version": 1,
  "updatedAt": "2026-07-07T00:00:00+00:00",
  "latestDrillRunId": null,
  "latestPatchId": null
}
```

### 5.2 Drill Admin response

`GET /api/courses/{courseId}/drill-runs/{drillRunId}` に追加する。

```json
{
  "drillFocus": "上限超過時の承認判断",
  "scoreSummary": {
    "gradedAnswerCount": 4,
    "averageScore": 2.1,
    "maxScore": 4,
    "questions": [
      {
        "questionId": "q2",
        "prompt": "上限を超える経費精算で必要な確認は何ですか？",
        "gradedAnswerCount": 4,
        "averageScore": 1.5,
        "maxScore": 4,
        "commonMissingPoints": ["事前承認への言及がない"],
        "failureTags": ["missing_prior_approval_step"]
      }
    ]
  },
  "analysisTimeline": [
    {
      "id": "collect_answers",
      "title": "回答データを収集",
      "status": "completed",
      "summary": "4 件の採点済み回答を確認。平均点は 2.1 / 4.0。",
      "evidence": ["回答数 4 件", "平均点 2.1 / 4.0"],
      "completedAt": "2026-07-07T00:00:00+00:00"
    }
  ]
}
```

受講者向け `LearnerDrillResponse` には `drillFocus`、`scoreSummary`、`analysisTimeline` を含めない。

### 5.3 Patch response

`GET /api/patches/{patchId}` に追加する。

```json
{
  "analysisTimeline": [
    {
      "id": "detect_failure_patterns",
      "title": "つまずき箇所を特定",
      "status": "completed",
      "summary": "q2 で 3 / 4 人が事前承認に触れていない。",
      "evidence": ["failureTags: missing_prior_approval_step"]
    }
  ]
}
```

### 5.4 Analyze flow

既存の API shape は維持する。

```text
POST /api/courses/{courseId}/drill-runs/{drillRunId}/analyze
-> { "patchId": "..." }
```

ただし frontend は POST を待っている間に `GET Drill Admin` を polling し、
`analysisTimeline` を更新表示する。

実装イメージ:

1. `Analyze answers` click
2. frontend が `api.analyzeDrill(...)` を開始
3. 同時に 1 秒間隔で `api.getDrill(...)` を polling
4. backend は `DrillRun.status = analyzing` と timeline を段階更新
5. POST が `patchId` を返したら Patch Review へ遷移
6. Patch Review は `DocumentPatch.analysisTimeline` を表示

この方式なら background job や SSE を追加せず、実進捗に近い UI を作れる。

## 6. Agent 設計

### 6.1 Drill generator input

agent / backend の両方で `drill_focus` を追加する。

```python
class DrillGenerationInput(AgentModel):
    course_title: str
    course_markdown: str
    drill_focus: str | None = Field(
        default=None,
        validation_alias=AliasChoices("drillFocus", "focus", "drill_focus"),
        serialization_alias="drillFocus",
    )
```

backend 側の `DrillGenerationRequest` も同じ field を持つ。

### 6.2 Drill generator prompt

追加ルール:

- `drillFocus` がある場合、設問の観点として優先する
- ただし `drillFocus` は根拠ではない
- すべての設問、rubric、idealAnswer、sourceEvidence は `courseMarkdown` の記述に基づける
- `drillFocus` が教材 Markdown に対応していない場合は、教材 Markdown に実在する内容だけで出題する
- `drillFocus` に含まれる業務ルール、数値、例外条件を courseMarkdown にない形で追加しない

### 6.3 根拠検証

`DrillService._validate_questions` は `course.markdown` を受け取り、次を検証する。

- 設問数は現行通り 3 問
- rubric 合計点は `maxScore`
- `sourceEvidence` は空でない
- 各 `sourceEvidence.excerpt.strip()` は空でない
- 各 `sourceEvidence.excerpt` は `course.markdown` に含まれる

検証失敗時は drill run を `failed` にし、既存の `drill generation failed` として扱う。

### 6.4 LocalAgentInvoker

local / CI 用 fallback も教材本文を読む。

最低要件:

- `courseMarkdown` の見出しまたは先頭本文から `sourceEvidence` を作る
- `drillFocus` がある場合は question / intent に反映する
- 固定の `判断基準` excerpt を返さない

これにより local mode でも「本文と無関係な問題が出る」体験を避ける。

### 6.5 Improvement Agent への移行

注: 単一 `improvement_agent` への統合方針は見送り、役割分離したマルチエージェント構成へ
発展させる方針に変更した。詳細は 15 章を参照。以下は当初案の記録として残す。

ハッカソン戦略上、最終的には `failure_analysis_agent` と `document_patch_agent` を
`improvement_agent` に統合する。

ただし本設計の UI/API は、現行の 2 agent 構成でも実装できる。

段階:

1. 既存構成のまま `AnalysisService` が timeline を組み立てる
2. `improvement_agent` を追加し、backend は `improve_document` task を呼ぶ
3. `ImprovementOutput` に `failureSignals`、`patchedMarkdown`、`patchSummary`、`riskNotes`、
   `analysisTimeline` を含める
4. backend は Pydantic で最終 JSON を検証する

ADK 注意:

- tools を使う自律 Agent には `output_schema` を付けない
- 最終出力の schema validation は backend 境界で行う

## 7. Backend 実装設計

### 7.1 CourseService

変更:

- create/update request の `drill_focus` を normalize する
- `drill_focus` 変更でも version を increment する
- `CourseRevision` に `drill_focus` を保存する

Validation helper:

```python
def _normalize_drill_focus(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None
```

### 7.2 DrillService

変更:

- `DrillRun` 作成時に `drill_focus=course.drill_focus` を保存する
- `DrillGenerationRequest` に `drill_focus=course.drill_focus` を渡す
- `_validate_questions(agent_response.questions, course.markdown)` に変更する
- `DrillAdminResponse` に `drill_focus`、`score_summary`、`analysis_timeline` を含める
- 採点済み `Answer` から owner-only の `score_summary` を組み立てる

### 7.3 AnalysisService

新規 helper:

```python
def _update_timeline(
    self,
    drill_run: DrillRun,
    item: AnalysisTimelineItem,
) -> DrillRun:
    ...
```

処理順:

1. `start_analysis`
   - `status = analyzing`
   - `collect_answers` を `running` で保存
2. graded answers を集計
   - `collect_answers` を `completed`
   - 平均点、回答数を `summary` / `evidence` に入れる
3. failure analysis 実行前
   - `detect_failure_patterns` を `running`
4. failure analysis 実行後
   - `detect_failure_patterns` を `completed`
   - 代表的な failure signal を要約
5. course evidence 照合
   - `match_course_evidence` を `completed`
   - `targetSections` と source excerpt を要約
6. patch 方針判断
   - `decide_patch_strategy` を `completed`
   - patch する理由、または将来の no-patch 理由を保存
7. document patch 実行
   - `create_patch` を `running` -> `completed`
8. `DocumentPatch.analysis_timeline` に最終 timeline をコピー

エラー時:

- 実行中 step を `failed` にする
- `DrillRun.status = failed`
- `errorMessage = analysis failed`

### 7.4 Repository

既存の `set_document` / `update` で対応できるため、新規 repository は作らない。
`DrillRun.analysisTimeline` は `DrillRepository.update` で保存する。

## 8. Frontend 実装設計

### 8.1 API types

追加:

```ts
export type AnalysisStepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export type AnalysisTimelineItem = {
  id: string
  title: string
  status: AnalysisStepStatus
  summary: string
  evidence: string[]
  completedAt: string | null
}

export type QuestionScoreSummary = {
  questionId: string
  prompt: string
  gradedAnswerCount: number
  averageScore: number | null
  maxScore: number
  commonMissingPoints: string[]
  failureTags: string[]
}

export type DrillScoreSummary = {
  gradedAnswerCount: number
  averageScore: number | null
  maxScore: number
  questions: QuestionScoreSummary[]
}
```

変更:

- `CoursePayload.drillFocus?: string | null`
- `CourseDetail.drillFocus: string | null`
- `DrillAdmin.drillFocus: string | null`
- `DrillAdmin.scoreSummary: DrillScoreSummary`
- `DrillAdmin.analysisTimeline: AnalysisTimelineItem[]`
- `DocumentPatch.analysisTimeline: AnalysisTimelineItem[]`

### 8.2 CourseEditorPage

追加 state:

```ts
const [drillFocus, setDrillFocus] = useState('')
```

保存 payload:

```ts
{
  title,
  markdown,
  drillFocus: drillFocus.trim() || null,
}
```

Validation:

- 500 文字超過なら `出題したい観点は 500 文字以内で入力してください。`

### 8.3 AnalysisTimeline component

`frontend/src/components/common/AnalysisTimeline.tsx` を追加する。

Props:

```ts
type AnalysisTimelineProps = {
  title: string
  items: AnalysisTimelineItem[]
}
```

表示:

- status chip
- title
- summary
- evidence list

依存方向:

- component は `api` を import しない
- `AnalysisTimelineItem` type は props 側で受ける。必要なら `api/types` から type-only import

### 8.4 DrillAdminPage

スコア表示:

- Analyze ボタンの上に `scoreSummary` を表示する
- 採点済み回答数、平均点、満点を compact に表示する
- 設問ごとの平均点を一覧表示し、低い設問がすぐ分かるようにする
- `commonMissingPoints` と `failureTags` は owner-only の補助情報として表示する
- `gradedAnswerCount === 0` の場合は `採点済み回答がまだありません` と表示し、Analyze ボタンは disabled にする

分析ボタン押下時:

- `api.analyzeDrill` promise を開始
- `setAnalysisState({ status: 'loading' })`
- polling timer で `api.getDrill` を呼び、`analysisTimeline` を更新
- promise resolve で Patch Review へ navigate
- promise reject で error banner
- cleanup で timer 停止

表示:

- `drill.drillFocus` があれば meta に表示
- `scoreSummary` は分析前から表示する
- `analysisTimeline.length > 0` のとき `AnalysisTimeline` を表示
- loading 中でも timeline を表示し続ける

### 8.5 PatchReviewPage

表示:

- patch summary の下、failure signals の前に `AnalysisTimeline` を表示
- timeline が空なら表示しない

## 9. 改善メトリクス設計

優勝狙いでは「AI が教材を更新した結果、理解度が上がった」ことを示す必要がある。
ただし、画面ごとに見せるメトリクスの役割を分ける。

### 9.1 画面ごとの役割

Drill Admin:

- 目的: 分析ボタンを押すべき理由を見せる
- 表示: 現在の平均点、採点済み回答数、設問ごとの平均点、よく抜ける観点
- タイミング: 分析前から表示する

Analysis Timeline:

- 目的: 分析 Agent が何を見ているかを進捗として見せる
- 表示: 分析対象回答数、平均点、低スコア設問、検出した failure signal
- タイミング: Analyze ボタン押下後に段階表示する

Patch Review:

- 目的: patch 提案の根拠を確認できるようにする
- 表示: 回答サンプル数、failure signal、target section、判断ログ、diff
- タイミング: 分析完了後に表示する

Course Editor / Course History:

- 目的: 教材更新による改善効果を見せる
- 表示: Before / After の平均点、回答数、教材 version、適用済み patch
- タイミング: patch 適用後、次の drill run の回答が集まった後に表示する

この分担にする理由:

- Drill Admin に Before / After まで出すと、分析前の画面として情報量が多すぎる
- Analyze 押下前に必要なのは「今どこが悪いか」
- Patch Review に必要なのは「なぜこの修正を提案したか」
- Course 側に必要なのは「教材が改善されたか」

### 9.2 優先順位

1. Drill Admin に現在の平均点と設問別スコアを出す
2. Analysis Timeline に平均点・低スコア設問・failure signal を出す
3. Patch Review に回答サンプル数と判断ログを出す
4. Course Editor / Course History に Before / After を出す

### P0

- Drill Admin に `scoreSummary.averageScore`、`gradedAnswerCount`、設問別平均点を表示
- Drill Admin に `commonMissingPoints` と `failureTags` を表示
- Patch Review に `回答サンプル N 件`
- Timeline に分析対象の平均点と低スコア設問を表示
- Failure Signal に sample size と evidence を表示

### P1

`GET /api/courses/{courseId}/metrics` を追加する。

Response:

```json
{
  "courseId": "course-1",
  "runs": [
    {
      "drillRunId": "drill-before",
      "courseVersion": 1,
      "answerCount": 4,
      "averageScore": 2.1,
      "maxScore": 4
    },
    {
      "drillRunId": "drill-after",
      "courseVersion": 2,
      "answerCount": 4,
      "averageScore": 3.4,
      "maxScore": 4
    }
  ]
}
```

UI:

- 第一候補: Course Editor の `講座の状態` エリアに比較カードを表示
- 第二候補: Course History に version ごとの平均点を表示
- Drill Admin には Before / After を置かない
- ハッカソン提出動画では `v1 平均 2.1 -> v2 平均 3.4` を最後のショットに使う

P1 は P0 完了後、デモデータを回しながら実装判断する。

## 10. テスト方針

### 10.1 Backend

追加・更新テスト:

- Course create/update が `drillFocus` を保存・返却する
- 空白 `drillFocus` は `None` になる
- 500 文字超過は validation error
- `drillFocus` 更新で version が増える
- Drill generation payload に `drillFocus` が含まれる
- DrillRun に生成時点の `drillFocus` が保存される
- Drill Admin response に `scoreSummary` が含まれる
- 採点済み回答が 0 件の場合、`scoreSummary.averageScore` は `None` になる
- `scoreSummary.questions` に設問ごとの平均点、missing points、failure tags が含まれる
- `sourceEvidence.excerpt` が course markdown にない場合、drill generation failed になる
- AnalysisService が timeline を段階保存する
- Analysis failure 時に running step が failed になる
- Patch に `analysisTimeline` が保存される

### 10.2 Agent

追加・更新テスト:

- `DrillGenerationInput` が `drillFocus` alias を受け取れる
- prompt に `drillFocus` と grounded 制約が含まれる
- evalset に `drillFocus` ありのケースを 1 件追加する
- local sample output は引き続き schema-valid

実 Gemini eval:

- 認証情報がある環境で `python scripts/run_adk_evals.py`
- 認証情報がない場合は通常 pytest と eval asset test まで実行

### 10.3 Frontend

追加・更新テスト:

- CourseEditor が `drillFocus` を入力・保存 payload に含める
- 500 文字超過時に validation error
- Course load 時に `drillFocus` がフォームに反映される
- DrillAdmin が `drillFocus`、`scoreSummary`、timeline を表示する
- DrillAdmin が採点済み回答 0 件のとき `採点済み回答がまだありません` を表示する
- DrillAdmin が設問ごとの平均点とよく抜ける観点を表示する
- Analyze 実行中に polling された timeline が表示される
- PatchReview が `analysisTimeline` を表示する
- Learner view に `drillFocus`、score summary、rubric、idealAnswer、analysisTimeline が出ない

## 11. 実装順

1. Backend / agent schema に `drillFocus` を追加
2. Course create/update/detail/revision に `drillFocus` を通す
3. Course Editor に `出題したい観点` を追加
4. Drill generation request に `drillFocus` を渡す
5. DrillRun / DrillAdmin に `drillFocus` snapshot を追加
6. Drill generator prompt と local invoker を grounded に修正
7. `sourceEvidence.excerpt` の backend 検証を追加
8. `DrillScoreSummary` を backend / frontend type に追加
9. DrillAdmin に分析前のスコア概要 UI を追加
10. `AnalysisTimelineItem` を backend / frontend type に追加
11. AnalysisService で timeline を保存
12. DrillAdmin の polling timeline UI を追加
13. PatchReview の判断ログ UI を追加
14. テスト更新
15. デモ教材で改善ループを複数回回し、提出用の強いケースを固定

## 12. 受け入れ条件

### 12.1 出題観点

Given オーナーが Course Editor に教材 Markdown と出題観点を入力する  
When 講座を保存してドリル生成する  
Then Agent への generate_drill payload に `drillFocus` が含まれる  
And Drill Admin に生成時の出題観点が表示される

### 12.2 根拠保証

Given Agent が教材 Markdown に存在しない `sourceEvidence.excerpt` を返す  
When backend が drill generation response を検証する  
Then drill run は failed になり、無根拠な設問は配布されない

### 12.3 スコア確認

Given 採点済み回答がある drill run  
When オーナーが Drill Admin を開く  
Then Analyze ボタンを押す前に平均点、採点済み回答数、設問ごとの平均点が表示される  
And 受講者画面には score summary が表示されない

### 12.4 分析タイムライン

Given 採点済み回答がある drill run  
When オーナーが回答分析を開始する  
Then Drill Admin に分析 Agent の実行状況が段階表示される  
And Patch Review に分析 Agent の判断ログが表示される

### 12.5 受講者情報の秘匿

Given 受講者が share URL を開く  
When ドリルに回答する  
Then score summary、rubric、idealAnswer、analysisTimeline、owner-only metadata は表示されない

## 13. リスクと対策

### リスク: 観点が教材にない

対策:

- prompt で `drillFocus` は根拠ではないと明記する
- backend で `sourceEvidence.excerpt` の本文存在チェックを行う
- 必要なら将来 `generationWarnings` を追加するが、P0 では追加しない

### リスク: timeline が Chain-of-thought に見える

対策:

- 表示するのは観測値、根拠、判断結果だけにする
- prompt や内部推論文を保存しない
- UI 文言は `実行状況` / `判断ログ` とする

### リスク: polling が複雑になる

対策:

- SSE / WebSocket / background worker は導入しない
- POST analyze は既存同期 API のまま
- frontend は POST promise と GET polling を併走するだけにする

### リスク: スコア改善が出ない

対策:

- 複数教材で実際に改善ループを回す
- デモには一番わかりやすい改善ケースを固定する
- 改善しないケースは「Agent が patch 不要と判断する」将来デモに回す

## 14. ハッカソン戦略メモ

DevOps × AI Agent Hackathon（Findy 主催、Google Cloud 協賛、提出締切 2026-07-10 23:59）
に向けた戦略の記録。

### 14.1 審査基準と賞

審査基準は 5 軸:

1. AI エージェント中心性: 自律的な振る舞いがあるか、AI エージェントである必然性があるか
2. 課題解決アプローチ: ストーリーの一貫性、妥当性、新規性
3. ユーザビリティ: 直観的で使いやすい機能とデザイン
4. 実用性・体験価値: 課題解決への実用性と突き抜けた体験価値
5. 実装力: 技術選定の納得度、拡張性、運用への配慮

賞: 最優秀賞 50 万円 x 1、優秀賞 30 万円 x 3、特別賞 10 万円 x 6。

必須技術: GCP 実行環境 1 つ以上（Cloud Run で充足）と
Google AI 技術 1 つ以上（Gemini API / ADK で充足）。

提出物: GitHub リポジトリ URL、動作確認可能なプロジェクト URL、ProtoPedia 作品ページ。

### 14.2 競合状況とポジショニング

提出済み約 30 作品の上位層は「コードのための DevOps × AI」に集中している。

- SRE 自走型: DevOps Lifecycle Agent、CloudMedic（検知 -> 診断 -> 修復 PR -> ポストモーテム）
- リリースゲート型: ReleaseGuard Agent、H.H.C.（PR を検証・ブロックする）
- チーム文脈型: Genos（Context OS）

この領域はレッドオーシャンであり、「AI がドリルを作る学習ツール」として並ぶと埋もれる。

Knowledge Drills の勝ち筋は、DevOps のフィードバックループを「知識・教材」に適用した
唯一の作品として語ること。対応表:

```text
コード                     -> 教材 Markdown
本番テレメトリ / インシデント -> 受講者の誤答データ
SRE / 障害分析              -> 分析 Agent（つまずき特定 -> 根拠照合 -> 方針判断）
修復 PR                    -> Markdown patch 提案
PR レビュー                 -> patch レビュー（オーナー apply + 検証 Agent）
デプロイ                   -> patch apply（Course version increment）
SLO 改善の確認              -> Before / After 平均点（v1 2.1 -> v2 3.4）
```

この対応付けは記事タイトル・冒頭・動画の最初の 15 秒で明示的に宣言する。
自分で言語化しないと「よくできた教育ツール」として基準 2 で減点される。

なお「DevOps テーマ = SRE 領域必須」ではない。評価観点の「つくる・まわす・とどける」の
うち、まわす・とどけるは自プロダクトの開発・運用プロセスの話であり、
Terraform + Workload Identity Federation + GitHub Actions + Cloud Run で既に満たしている。
「このプロダクト自体も DevOps で回っている」ことをアーキテクチャ図付きで記事に書く。

### 14.3 エージェントの必然性の語り方

「賢さ」と「Agentic であること」を分けて語る。

なぜ AI が必要か（ループの評価器として）:

- 誤答は非構造テキストで、教材の意味と突き合わせないと原因を特定できない
- ルールベースの critic は書けず、人間の講師では回らない

なぜエージェントか（単発の LLM 呼び出しではなく）:

- 分析の仕事が単発推論で終わらない構造を持つ
  1. 観測: 採点済み回答を集計する
  2. 照合: つまずき箇所を教材 Markdown の該当セクションと突き合わせる
  3. 診断の分岐: 教材の記述不足か、設問が悪いのか、受講者個別の問題かを場合分けする
  4. 行動の分岐: patch を出すか出さないか、どのセクションに出すかを決める
  5. 検証: patch が既存ルールを壊さないか、根拠が教材に実在するかを確認する
- 3 と 4 に「入力によって結論が変わる判断の分岐」があることが必然性の実体

ハーネス論（賢さは拡張性の主張に使う）:

- 本システムは、教材というポリシーを受講者の回答というロールアウトで継続的に最適化する
  ハーネスであり、分析 Agent は critic の位置にいる
- 分析 Agent がループのボトルネックかつレバレッジポイントになるよう設計してあるため、
  モデルが次世代 Gemini に置き換わるだけでシステム全体の教材改善能力が上がる
- これは基準 1（必然性）ではなく基準 5（拡張性）の主張として使う

デモで自律判断を見せる強いケース:

- Agent が patch 不要と判断するケース（言いなりの生成器ではない証明）
- 教材ではなく設問側に問題があると診断するケース（実装が間に合わなければ
  `decide_patch_strategy` の判断理由表示だけでも主張は成立する）

### 14.4 提出までの優先順位

1. P0（根拠検証、scoreSummary、分析タイムライン）を完遂する。
   タイムラインは「自律的に判断している証拠」を画面に出す機能であり基準 1 に直結する
2. P1 の Before / After メトリクスを最優先に格上げする。
   「v1 平均 2.1 -> v2 平均 3.4」の 1 ショットが本作品の最強の証拠
3. デモ用教材で実際にループを 2 周以上回し、一番きれいな改善ケースを固定する
4. 審査員が触れる導線を整える。ログイン不要で回答 -> 採点まで体験できる
   受講者用 share URL を ProtoPedia 記事の最上部に置く
5. 動画は 3 分以内で
   「教材投入 -> 観点入力 -> ドリル生成 -> 誤答 -> 分析タイムライン -> patch 適用 -> スコア改善」
   のループを 1 本で見せ、最後のショットは改善グラフで締める
6. drillFocus は勝敗への寄与が小さい。時間が逼迫したら削る候補の筆頭

## 15. マルチエージェント構成方針

### 15.1 方針

役割分離したマルチエージェント + agentic workflow の複合構成にする。
自由討論型の swarm は採用しない。

### 15.2 マルチエージェントの必然性

「シングルエージェントではできないから」という主張は立たない
（ツールを持ったシングルエージェントでも実行自体は可能なため）。

立つ論理は提案者と検証者の独立性:

- patch を書いた主体が、その patch の妥当性を自己採点してはいけない
- コードの author と reviewer を分けるのと同じ理由で、
  分析 Agent と評価 Agent は別の context を持つ別の主体である必要がある
- これは patch = PR という本作品の DevOps メタファーにおいて
  「PR レビュー」に対応し、ストーリーの一貫性（基準 2）を同時に強化する
- 役割ごとの context 分離はハルシネーションの連鎖を断つという実装力の主張にもなる

### 15.3 agentic workflow は弱くない

基準 1 が見るのはトポロジーの自由さではなく判断の自律性。
オーケストレーションが固定でも、各ステップ内に入力依存の分岐
（patch する / しない、教材が悪い / 設問が悪い）があれば自律性の要件は満たす。

固定パイプラインの積極的な利点:

- 本作品の差別化ポイントである分析タイムライン（監査可能な判断ログ）を綺麗に出せる
- 「再現性と監査可能性のために deterministic orchestration + autonomous judgment を
  選んだ」という本番運用を見据えた設計判断として語れる（基準 5 の運用への配慮に直結）

### 15.4 swarm 議論を採用しない理由

- 議論ログは長く発散的で、タイムライン UI の「観測 -> 根拠 -> 判断」の形にならず、
  自作品の武器である監査ログを壊す
- 誤答分析というタスクで討論が精度を上げる根拠を締切までに示せず、
  エージェントを増やすこと自体は加点されない
- 非決定的なシステムのデモを残り日数で固定するのは工数リスクが大きすぎる

多視点が必要な場合は swarm ではなく、視点を固定した並列分析にする
（ルーブリック観点 / 教材ギャップ観点 / 設問品質観点の 3 レンズで並列に分析し、
統合ステップが結論を出す）。出力が構造化されるためタイムラインに載り、デモも安定する。

### 15.5 推奨構成

ADK の `SequentialAgent` / `ParallelAgent` を使う:

```text
評価 Agent（採点・既存）
  -> 分析: ParallelAgent [教材ギャップ / 設問品質 / つまずきパターン]
  -> 統合・方針判断 Agent（patch 要否・対象を決定）
  -> patch 生成 Agent
  -> patch レビュー Agent（独立検証: 根拠実在・既存ルール非破壊）
```

協賛技術である ADK のマルチエージェント機能を正しく使っている証拠にもなる。

### 15.6 優先順位

この改造は P0（根拠検証・タイムライン）と Before / After メトリクスの完了後に着手する。
マルチエージェント化は「必然性の語り」を強化する磨き込みであり、
勝敗を決める 1 ショットは Before / After の改善グラフである。

時間が尽きた場合は patch レビュー Agent（独立検証）だけを追加する。
これだけで DevOps メタファー（PR レビュー）が完成し、費用対効果が最大になる。
