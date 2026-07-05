# Knowledge Drill MVP 仕様書

Version: 0.3  
Date: 2026-06-29  
Stack: Vite, Python FastAPI, Google Cloud, Agent Platform / Agent Runtime

## 1. 目的

Knowledge Drill は、Markdown 講座を実務シナリオ型ドリルに変換し、受講者の誤答から講座改善の Document Patch を生成する Knowledge CI アプリケーションである。

MVP の検証仮説は次の 1 点に絞る。

> 受講者の誤答から生成された Document Patch は、講座オーナーにとって講座改善に使えるのか。

MVP では、以下の流れを実装する。

```text
course.md
  -> Drill generation
  -> Learner answers
  -> Grading
  -> Failure signals
  -> Document patch
  -> Owner review
  -> Apply / Reject
```

PDF アップロード、画像対応、GitHub PR 作成、LMS 連携、本格的な権限管理、問題バンクは MVP では扱わない。

## 2. 技術構成

### 2.1 Frontend

- Vite
- React
- TypeScript
- React Router
- textarea ベースの Markdown editor
- diff viewer

### 2.2 Backend

- Python 3.11+
- FastAPI
- Pydantic
- Google Cloud Firestore SDK
- Google Cloud Agent Platform SDK for Python
- Python `difflib` または同等ライブラリによる unified diff 生成

### 2.3 Agent

- Google ADK で Agent を実装する
- Gemini Enterprise Agent Platform の Agent Runtime にデプロイする
- FastAPI から Agent Runtime 上の remote agent を呼び出す
- Agent の出力は Pydantic schema で検証する

注記: Python API の名前空間として `agent_engines` が登場する場合があるが、仕様書内の製品名は Agent Platform / Agent Runtime に統一する。

### 2.4 Infrastructure

- Cloud Run: FastAPI backend
- Firebase Hosting または Cloud Run: Vite frontend
- Firestore: application data
- Agent Runtime: Agent execution
- Vertex AI / Gemini: model execution
- Secret Manager: API keys, service config
- Cloud Logging: backend and agent logs
- Cloud Build: CI/CD
- Artifact Registry: container images

## 3. システム構成

```text
Browser
  |
  v
Vite Frontend
  |
  v
FastAPI Backend on Cloud Run
  |
  |-- Firestore
  |     |-- courses
  |     |-- drill_runs
  |     |-- answers
  |     |-- patches
  |

  
  |-- Agent Platform / Agent Runtime
        |-- DrillGeneratorAgent
        |-- GradingAgent
        |-- FailureAnalysisAgent
        |-- DocumentPatchAgent
        |
        v
      Gemini model
```

FastAPI はアプリケーションの信頼境界を担う。Agent は講座理解、問題生成、採点、分析、改善案生成を担う。Firestore 更新、shareToken 検証、diff 生成、patch apply/reject は FastAPI 側で行う。

## 4. 画面仕様

### 4.1 Course Editor

URL:

```text
/courses/:courseId
```

目的:

講座オーナーが `course.md` を入力、保存し、ドリル生成を開始する。

表示要素:

- Course title
- Markdown textarea
- Save button
- Generate drill button
- Latest drill run
- Latest patch

MVP では Markdown preview は任意とする。

### 4.2 Drill Admin / Share Page

URL:

```text
/courses/:courseId/drill-runs/:drillRunId
```

目的:

生成されたドリルを確認し、受講者向け URL を共有する。

表示要素:

- Generated questions
- Rubric summary
- Share URL
- Answer count
- Analyze answers button

MVP では問題は 3 問固定、形式は記述式のみとする。

### 4.3 Learner Answer Form

URL:

```text
/drills/:shareToken
```

目的:

受講者がドリルに回答する。

表示要素:

- Learner name
- Question 1-3
- Answer textarea
- Submit button
- Submission result
- Minimal feedback

受講者向け API レスポンスには `rubric` と `idealAnswer` を含めない。

### 4.4 Analysis & Patch Review

URL:

```text
/courses/:courseId/drill-runs/:drillRunId/analysis
```

目的:

回答結果、共通誤答、Document Patch diff を確認する。

表示要素:

- Answer summary
- Average score
- Failure signals
- Patch summary
- Risk notes
- Unified diff viewer
- Owner feedback textarea
- Apply button
- Reject button

## 5. Agent 設計

MVP では Agent を 4 つに分ける。実装上は ADK の複数 Agent として定義し、Agent Runtime にデプロイする。

### 5.1 DrillGeneratorAgent

責務:

`course.md` から実務シナリオ型の記述式ドリルを 3 問生成する。

入力:

```json
{
  "courseTitle": "新卒向け会社理解講座",
  "courseMarkdown": "# 新卒向け会社理解講座\n..."
}
```

出力:

```json
{
  "questions": [
    {
      "id": "q1",
      "question": "顧客から既存契約の変更に関する問い合わせを受けました...",
      "intent": "新規契約と既存契約変更の相談先を区別できるか確認する",
      "rubric": [
        {
          "criterion": "既存契約変更であることを識別している",
          "points": 1,
          "required": true
        }
      ],
      "idealAnswer": "既存契約の変更に関する問い合わせなので...",
      "sourceEvidence": [
        {
          "sectionHeading": "相談先判断",
          "excerpt": "A事業部は新規契約を担当します。B事業部は既存顧客を担当します。"
        }
      ]
    }
  ]
}
```

生成ルール:

- 3 問生成する
- すべて実務シナリオ型にする
- 単なる用語説明問題にしない
- 受講者に判断理由を書かせる
- 各問に rubric を付ける
- 各問の満点は 4 点
- `course.md` に根拠がある内容だけを問う
- `sourceEvidence` を必ず付ける

### 5.2 GradingAgent

責務:

受講者の記述回答を rubric に基づいて採点する。

入力:

```json
{
  "question": "...",
  "rubric": [],
  "idealAnswer": "...",
  "learnerAnswer": "..."
}
```

出力:

```json
{
  "score": 2,
  "maxScore": 4,
  "correctPoints": ["契約に関する問い合わせであることは認識している"],
  "missingPoints": ["既存契約変更の場合はB事業部に相談する判断が抜けている"],
  "feedback": "契約に関する問い合わせであることは認識できていますが...",
  "failureTags": ["confused_new_contract_and_existing_contract"]
}
```

採点ルール:

- rubric に従う
- 回答に書かれていないことを補完しない
- 良い点と不足点を分ける
- 後続分析に使える `failureTags` を付ける

### 5.3 FailureAnalysisAgent

責務:

複数回答と採点結果から、共通する誤答傾向を Failure Signal として抽出する。

入力:

```json
{
  "courseMarkdown": "...",
  "questions": [],
  "answers": [],
  "gradingResults": []
}
```

出力:

```json
{
  "failureSignals": [
    {
      "id": "fs_001",
      "title": "既存契約変更の相談先をA事業部と誤答する傾向",
      "severity": "high",
      "sampleSize": 5,
      "evidence": ["5人中3人が既存契約変更の相談先をA事業部と回答"],
      "confidenceNote": "回答数が十分ではないため、追加回答で傾向を確認してください。",
      "likelyCause": "契約という単語だけでA事業部を選んでいる",
      "suspectedDocumentGap": "新規契約と既存契約変更の判断基準が明文化されていない",
      "targetSections": ["相談先判断"],
      "recommendedChange": "相談先判断の基準を具体的に追記する"
    }
  ]
}
```

分析ルール:

- 個別の誤答ではなく共通パターンを見る
- 回答数が少ない場合は断定せず、`sampleSize` と `confidenceNote` で少数回答に基づく傾向であることを明示する
- 受講者の理解不足と講座ドキュメントの説明不足を分ける
- 改善対象セクションを示す
- 事実として確認できない会社ルールは新しく作らない

### 5.4 DocumentPatchAgent

責務:

`course.md` と Failure Signals から、改善後の `patchedMarkdown` を生成する。

入力:

```json
{
  "courseMarkdown": "...",
  "failureSignals": []
}
```

出力:

```json
{
  "patchedMarkdown": "...",
  "patchSummary": "相談先判断セクションに判断基準を追記しました。",
  "riskNotes": [
    "B事業部が既存契約変更を担当するという記述は、元のcourse.mdの情報に基づいています。実運用と一致するか確認してください。"
  ]
}
```

Patch 生成ルール:

- `course.md` 全体を返す
- 既存構造をなるべく維持する
- Failure Signal に対応する最小限の修正を行う
- 会社ルールを新規に創作しない
- 不確かな内容は `riskNotes` に出す
- Markdown 構造を壊さない

## 6. Agent Platform / Agent Runtime 連携仕様

### 6.1 デプロイ単位

Agent は 1 つの Agent app として Gemini Enterprise Agent Platform の Agent Runtime にデプロイする。

推奨構成:

```text
knowledge_drill_agent/
  agent.py
  schemas.py
  prompts/
    drill_generator.md
    grading.md
    failure_analysis.md
    document_patch.md
```

`agent.py` には root agent と専門 Agent を定義する。FastAPI からは operation 名または request payload の `task` によって処理を分岐する。

### 6.2 FastAPI からの呼び出し

FastAPI は次の用途で Agent Runtime 上の remote agent を呼び出す。

```text
POST /api/courses/:courseId/drill-runs
  -> DrillGeneratorAgent

POST /api/drills/:shareToken/answers
  -> GradingAgent

POST /api/courses/:courseId/drill-runs/:drillRunId/analyze
  -> FailureAnalysisAgent
  -> DocumentPatchAgent
```

Agent 呼び出しは同期でよい。ただし 30 秒を超える可能性がある場合は、後続フェーズで Cloud Tasks または background job 化する。

### 6.3 Agent 入出力の検証

Agent からの出力はすべて FastAPI 側で Pydantic schema に通す。

検証失敗時:

1. 同じ入力で 1 回だけ再実行する
2. それでも失敗した場合は Firestore に failed status と error reason を保存する
3. UI には retry 可能なエラーメッセージを返す

### 6.4 Agent に渡してよい情報

渡してよい情報:

- course title
- course markdown
- drill questions
- learner answers
- grading results

渡さない情報:

- Firestore document path の内部詳細
- Secret
- 管理者用 token
- 受講者に返してはいけない rubric / idealAnswer を含む API response

### 6.5 Agent Runtime の責務外

次の処理は Agent に任せない。

- shareToken 生成
- 認可判断
- Firestore 書き込み
- patch apply/reject
- `baseMarkdown` と現在の `course.markdown` の一致確認
- unified diff 生成

## 7. データモデル

### 7.1 courses

```ts
type Course = {
  id: string;
  title: string;
  markdown: string;
  version: number;
  createdAt: Timestamp;
  updatedAt: Timestamp;
  latestDrillRunId?: string;
  latestPatchId?: string;
};
```

### 7.2 drill_runs

```ts
type DrillRun = {
  id: string;
  courseId: string;
  courseVersion: number;
  status: "generating" | "ready" | "failed" | "analyzing" | "analyzed";
  questions: DrillQuestion[];
  shareToken: string;
  createdAt: Timestamp;
  updatedAt: Timestamp;
  errorMessage?: string;
};

type DrillQuestion = {
  id: string;
  question: string;
  intent: string;
  rubric: RubricItem[];
  idealAnswer: string;
  sourceEvidence: SourceEvidence[];
};

type RubricItem = {
  criterion: string;
  points: number;
  required: boolean;
};

type SourceEvidence = {
  sectionHeading: string;
  excerpt: string;
};
```

### 7.3 answers

```ts
type AnswerSubmission = {
  id: string;
  courseId: string;
  drillRunId: string;
  status: "grading" | "graded" | "failed";
  learnerName: string;
  answers: LearnerAnswer[];
  gradingResults?: GradingResult[];
  totalScore?: number;
  maxScore?: number;
  errorMessage?: string;
  createdAt: Timestamp;
  updatedAt: Timestamp;
};

type LearnerAnswer = {
  questionId: string;
  answerText: string;
};

type GradingResult = {
  questionId: string;
  score: number;
  maxScore: number;
  correctPoints: string[];
  missingPoints: string[];
  feedback: string;
  failureTags: string[];
};
```

### 7.4 patches

```ts
type DocumentPatch = {
  id: string;
  courseId: string;
  drillRunId: string;
  status: "proposed" | "applied" | "rejected" | "stale";
  failureSignals: FailureSignal[];
  baseMarkdown: string;
  patchedMarkdown: string;
  diffText: string;
  patchSummary: string;
  riskNotes: string[];
  ownerFeedback?: string;
  createdAt: Timestamp;
  appliedAt?: Timestamp;
};

type FailureSignal = {
  id: string;
  title: string;
  severity: "low" | "medium" | "high";
  sampleSize: number;
  evidence: string[];
  confidenceNote?: string;
  likelyCause: string;
  suspectedDocumentGap: string;
  targetSections: string[];
  recommendedChange: string;
};
```

## 8. API 仕様

### 8.1 Course 作成

```text
POST /api/courses
```

Request:

```json
{
  "title": "新卒向け会社理解講座",
  "markdown": "# 新卒向け会社理解講座\n..."
}
```

Response:

```json
{
  "courseId": "course_001"
}
```

### 8.2 Course 取得

```text
GET /api/courses/:courseId
```

### 8.3 Course 更新

```text
PUT /api/courses/:courseId
```

### 8.4 Drill 生成

```text
POST /api/courses/:courseId/drill-runs
```

処理:

1. course を取得する
2. `course.markdown` が 20,000 文字以内であることを確認する
3. Firestore に `status = generating` の drill_run を作成する
4. Agent Runtime 上の DrillGeneratorAgent を呼ぶ
5. 出力 schema を検証する
6. shareToken を生成する
7. drill_run を `status = ready` に更新する

Response:

```json
{
  "drillRunId": "drill_001",
  "shareUrl": "/drills/abc123"
}
```

### 8.5 Learner Drill 取得

```text
GET /api/drills/:shareToken
```

Response には `rubric` と `idealAnswer` を含めない。

無効な `shareToken` の場合:

- HTTP 404 を返す
- response body には `{"error": "invalid_share_token"}` を含める
- drill_run、rubric、idealAnswer は返さない

### 8.6 回答提出

```text
POST /api/drills/:shareToken/answers
```

処理:

1. shareToken から drill_run を取得する
2. 無効な `shareToken` の場合は HTTP 404 と `{"error": "invalid_share_token"}` を返し、answer は作成しない
3. learnerName と answers を検証する
4. 検証に失敗した場合は HTTP 400 を返し、answer は作成しない
5. `status = grading` の answer を作成し、learnerName と answers を保存する
6. 各回答に対して GradingAgent を呼ぶ
7. gradingResults を保存し、answer を `status = graded` に更新する
8. 受講者向けの簡易 feedback を返す

採点失敗時:

1. 同じ入力で 1 回だけ再実行する
2. それでも失敗した場合は answer を `status = failed` に更新し、`errorMessage` を保存する
3. UI には retry 可能なエラーメッセージを返す

### 8.7 Analysis & Patch 生成

```text
POST /api/courses/:courseId/drill-runs/:drillRunId/analyze
```

処理:

1. course を取得する
2. drill_run を取得する
3. answers を取得する
4. FailureAnalysisAgent を呼ぶ
5. DocumentPatchAgent を呼ぶ
6. backend 側で `baseMarkdown` と `patchedMarkdown` の unified diff を生成する
7. patch を `status = proposed` で保存する

Response:

```json
{
  "patchId": "patch_001"
}
```

### 8.8 Patch 取得

```text
GET /api/patches/:patchId
```

処理:

1. patch を取得する
2. course を取得する
3. `patch.status == proposed` かつ `patch.baseMarkdown != course.markdown` の場合、patch を `status = stale` に更新する
4. patch の現在状態、Failure Signal、diff、patchSummary、riskNotes、ownerFeedback を返す

Patch Review UI は stale 状態を受け取った場合、Apply を実行不可にし、再分析を促す。

### 8.9 Patch 適用

```text
POST /api/patches/:patchId/apply
```

Request:

```json
{
  "ownerFeedback": "この改善案を適用します。"
}
```

処理:

1. patch を取得する
2. `patch.status == proposed` を確認する
3. course を取得する
4. `patch.baseMarkdown == course.markdown` を確認する
5. course.markdown を `patch.patchedMarkdown` で更新する
6. course.version を +1 する
7. `ownerFeedback` が入力されている場合は patch.ownerFeedback に保存する
8. patch.status を `applied` にする
9. patch.appliedAt を保存する

`patch.status != proposed` の場合は HTTP 409 を返し、response body には `{"error": "patch_not_proposed", "currentStatus": "<patch.status>"}` を含める。course は更新しない。

`baseMarkdown` が一致しない場合は patch を `stale` にし、再分析を促す。

### 8.10 Patch 却下

```text
POST /api/patches/:patchId/reject
```

Request:

```json
{
  "ownerFeedback": "この変更は講座方針と合わないため却下します。"
}
```

処理:

1. patch を取得する
2. `patch.status == proposed` を確認する
3. course を取得する
4. `patch.baseMarkdown == course.markdown` を確認する
5. `ownerFeedback` が入力されている場合は patch.ownerFeedback に保存する
6. patch.status を `rejected` にする

`patch.status != proposed` の場合は HTTP 409 を返し、response body には `{"error": "patch_not_proposed", "currentStatus": "<patch.status>"}` を含める。patch は更新しない。

`baseMarkdown` が一致しない場合は patch を `stale` にし、再分析を促す。

## 9. バリデーション

### 9.1 Course

- title は 1 文字以上
- markdown は 1 文字以上
- markdown は MVP では 20,000 文字以下

### 9.2 Drill generation

- `questions.length == 3`
- 各 question に rubric がある
- 各 question に idealAnswer がある
- 各 question に sourceEvidence がある
- rubric の points 合計が 4
- question が短すぎない

### 9.3 Answer submission

- learnerName は空にしない
- questionId は drill_run 内の question と一致する
- answerText は空にしない
- 短すぎる回答は受け付けるが、採点では不足として扱う

### 9.4 Analysis

- answer は 1 件以上必要
- 3 件未満の場合は Failure Signal に `sampleSize` と `confidenceNote` を含める
- evidence には具体的な回答数または観測事実を含める

## 10. セキュリティ

MVP ではログインなしでも検証可能とする。ただし次は必須とする。

- shareToken は推測困難なランダム文字列にする
- 受講者 API から rubric と idealAnswer を返さない
- 本物の機密社内資料は使わない
- Secret は Secret Manager に保存する
- Cloud Run service account に最小権限を付与する
- Agent Runtime 呼び出し権限は backend service account に限定する
- Patch は人間の承認なしに適用しない

## 11. LLM / Agent 安全性

DocumentPatchAgent には次の制約を必ず含める。

- 会社ルールを勝手に作らない
- `course.md` にある情報から安全に明確化できる範囲で修正する
- 不確かな内容は `riskNotes` に出す
- 変更は Failure Signal に対応する箇所に限定する
- 人間の承認なしに course を更新しない

FailureAnalysisAgent には次の制約を必ず含める。

- 受講者を責める表現にしない
- 回答数が少ない場合は傾向として表現する
- ドキュメントの説明不足と受講者の理解不足を分ける

## 12. 非機能要件

### 12.1 Performance

- course markdown は 20,000 文字まで
- drill 生成は MVP では同期でよい
- analysis も MVP では同期でよい
- Agent 呼び出しが長くなる場合は timeout と retry を設ける

### 12.2 Observability

Cloud Logging に次を記録する。

- request id
- courseId
- drillRunId
- patchId
- agent task name
- agent execution latency
- validation error reason

ログに learner answer の全文を出すかどうかは検証環境のデータ感度に応じて制限する。

### 12.3 Error handling

Agent 失敗時:

- 対象 document に failed status と error reason を保存する
- UI に retry 可能な状態として表示する

Patch stale 時:

- `patch.status = stale`
- UI に「このPatch生成後にcourse.mdが編集されています。再分析してください。」と表示する

## 13. 実装順序

### Phase 1: 基本 CRUD

- Vite app scaffold
- FastAPI scaffold
- Firestore 接続
- Course create / get / update
- Course Editor

### Phase 2: Agent Runtime 基盤

- ADK agent project 作成
- schema 定義
- DrillGeneratorAgent 実装
- local evaluation
- Agent Runtime へ deploy
- FastAPI から remote agent 呼び出し

### Phase 3: Drill 生成

- `POST /api/courses/:courseId/drill-runs`
- drill_runs 保存
- Drill Admin page
- Share URL 表示

### Phase 4: 回答と採点

- Learner Answer Form
- GradingAgent
- answers 保存
- feedback 表示

### Phase 5: 分析と Patch

- FailureAnalysisAgent
- DocumentPatchAgent
- backend diff 生成
- Patch Review UI

### Phase 6: Apply / Reject

- Patch apply
- Patch reject
- stale check
- owner feedback 保存

## 14. 受け入れ条件

### 14.1 Course Editor

Given 講座オーナーが `course.md` を入力する  
When Save を押す  
Then Firestore に markdown が保存される

### 14.2 Drill 生成

Given `course.md` が保存されている  
When Generate Drill を押す  
Then Agent Runtime 経由で実務シナリオ型の記述問題が 3 問生成される  
And 各問題に rubric がある  
And 各問題に sourceEvidence がある

### 14.3 回答提出

Given 受講者が share URL を開く  
When 3 問に回答して Submit する  
Then 回答が保存される  
And Agent Runtime 経由で採点結果が保存される

### 14.4 Failure Analysis

Given 複数の回答が保存されている  
When Analyze Answers を押す  
Then Agent Runtime 経由で共通誤答パターンが Failure Signal として生成される

### 14.5 Document Patch

Given Failure Signal が生成されている  
When DocumentPatchAgent が実行される  
Then `patchedMarkdown` が生成される  
And backend 側で diff が生成される

### 14.6 Patch 適用

Given proposed patch が存在する  
When 講座オーナーが Apply を押す  
Then course.markdown が patchedMarkdown に更新される  
And course.version が増える  
And patch.status が applied になる

## 15. MVP 完成ライン

MVP は次を満たせば完成とする。

- `course.md` を入力・保存できる
- Agent Runtime 経由で 3 問のドリルを生成できる
- 受講者が share URL から回答できる
- Agent Runtime 経由で回答を採点できる
- Agent Runtime 経由で誤答傾向を Failure Signal として出せる
- Agent Runtime 経由で `patchedMarkdown` を生成できる
- backend 側で diff を生成できる
- 講座オーナーが Apply / Reject できる

## 16. 参考ドキュメント

- Google Cloud Run: https://cloud.google.com/run/docs
- Firestore: https://cloud.google.com/firestore/docs
- Gemini Enterprise Agent Platform / Agent Runtime overview: https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime
- Agent Runtime quickstart with ADK: https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk
