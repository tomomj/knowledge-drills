# Knowledge Drill Frontend ルーティング再設計・UI 改善仕様書

Version: 0.1
Date: 2026-07-05
Base: `docs/knowledge-drill-agent-engine-spec.md` v0.3

## 1. 目的

現行のフロントエンド実装は、MVP 仕様書 §4 の画面仕様と URL 設計・画面導線の両面で乖離している。本仕様書は次の 4 点を定義する。

1. 講座中心の URL 階層への再設計と、URL からの講座ロード
2. 画面間導線の整備（アプリシェル、パンくず、リンク化、コピー機能）
3. UI 改善（ボタン階層、diff viewer の色分け、Answer summary / Average score 表示）
4. API パスとフィールド名の MVP 仕様書への整合（backend ルート変更を含む）

## 2. 現状の課題

### 2.1 ルーティングの乖離

| 画面 | MVP 仕様書 | 現行実装 |
| --- | --- | --- |
| Course Editor | `/courses/:courseId` | `/courses`（courseId なし） |
| Drill Admin | `/courses/:courseId/drill-runs/:drillRunId` | `/drill-runs/:drillRunId` |
| Learner Answer Form | `/drills/:shareToken` | `/learn/:shareToken` |
| Analysis & Patch Review | `/courses/:courseId/drill-runs/:drillRunId/analysis` | `/patches/:patchId` |

これにより次の問題が発生している。

- Course Editor が URL パラメータを受け取らず `GET /api/courses/:courseId` を呼ばないため、リロードすると講座コンテキストが失われ、保存済み講座に二度と戻れない
- 画面間の導線がなく、Drill Admin や Patch Review から講座へ戻る手段がない
- Course Editor の Latest drill / Latest patch、Drill Admin の Share URL が素のテキスト表示でリンクになっていない

### 2.2 API の乖離

| MVP 仕様書 | 現行実装 |
| --- | --- |
| `GET /api/drills/:shareToken` | `GET /api/learn/:shareToken` |
| `POST /api/drills/:shareToken/answers` | `POST /api/learn/:shareToken/answers` |
| `GET /api/courses/:courseId/drill-runs/:drillRunId` | `GET /api/drill-runs/:drillRunId` |
| `POST /api/courses/:courseId/drill-runs/:drillRunId/analyze` | `POST /api/drill-runs/:drillRunId/analysis` |

フィールド名の乖離:

| MVP 仕様書 | 現行実装 |
| --- | --- |
| `question.question` | `question.scenario` |
| `failureSignal.likelyCause` | `failureSignal.inferredCause` |
| `failureSignal.suspectedDocumentGap` | `failureSignal.suspectedDocGap` |

### 2.3 UI の課題

- アプリシェル（ヘッダー、アプリ名、ナビゲーション）が存在しない
- 全ボタンが同一スタイルで、主要アクションと副次アクションの区別がない
- diff viewer が色分けのない生テキスト表示
- Patch Review の Average score が `-` にハードコードされており、仕様書 §4.4 の Answer summary / Average score が未実装（backend レスポンスにも含まれていない）

## 3. ルーティング仕様

### 3.1 ルート定義

```text
/                                                      -> /courses/new へ redirect
/courses/new                                           Course Editor（新規作成モード）
/courses/:courseId                                     Course Editor（編集モード）
/courses/:courseId/drill-runs/:drillRunId              Drill Admin
/courses/:courseId/drill-runs/:drillRunId/analysis     Analysis & Patch Review
/drills/:shareToken                                    Learner Answer Form
```

講座一覧 API は存在しないため、講座一覧画面はスコープ外とする（§9 参照）。

### 3.2 Course Editor

- `/courses/new` では空のフォームを表示する
- Save 成功時に `POST /api/courses` の結果から `navigate('/courses/:courseId', { replace: true })` で正規 URL へ遷移する
- `/courses/:courseId` ではマウント時に `GET /api/courses/:courseId` で講座をロードし、フォームに反映する
- 存在しない courseId の場合は 404 エラーバナーを表示する
- リロードしても講座コンテキストが失われないこと

### 3.3 Drill Admin / Analysis

- Drill Admin と Analysis は講座配下のネスト URL とし、URL の `courseId` と drill run の `courseId` の不一致時は 404 エラーバナーを表示する
- Generate drill 成功時は `/courses/:courseId/drill-runs/:drillRunId` へ遷移する
- Analyze answers 成功時は `/courses/:courseId/drill-runs/:drillRunId/analysis` へ遷移する
- Analysis 画面は drill run の最新 patch を表示する。取得手順: `GET /api/courses/:courseId/drill-runs/:drillRunId` のレスポンスに追加する `latestPatchId` を参照し、`GET /api/patches/:patchId` で patch を取得する
- `latestPatchId` が null の場合は「まだ分析されていません」と表示し、Drill Admin への導線を出す

### 3.4 Learner Answer Form

- `/drills/:shareToken` に変更する（機能は現行のまま）
- Learner 画面はオーナー向け導線（パンくず、講座リンク）を表示しない

## 4. 画面導線仕様

### 4.1 アプリシェル

オーナー向け画面（Course Editor / Drill Admin / Analysis）に共通レイアウトを導入する。

- ヘッダー: アプリ名「Knowledge Drill」（クリックで `/` へ）
- パンくず: 現在位置を表示する

```text
Course Editor:  講座
Drill Admin:    講座 > ドリル
Analysis:       講座 > ドリル > 分析
```

- パンくずの各要素は該当画面へのリンクにする
- React Router のレイアウトルート（`<Outlet />`）で実装する

### 4.2 リンク化とコピー機能

- Course Editor の Latest drill を Drill Admin へのリンクにする
- Course Editor の Latest patch を Analysis へのリンクにする（`latestDrillRunId` と組み合わせて URL を構築する）
- Drill Admin の Share URL を、絶対 URL のテキスト表示 + コピーボタンにする
- コピーボタンは `navigator.clipboard.writeText` を使い、成功時に「コピーしました」を一時表示する

## 5. UI 改善仕様

### 5.1 ボタン階層

- primary / secondary / danger の 3 種類のボタンスタイルを定義する

| 画面 | primary | secondary | danger |
| --- | --- | --- | --- |
| Course Editor | Save | Generate drill | - |
| Drill Admin | Analyze answers | Copy share URL | - |
| Analysis | Apply | - | Reject |

- primary はブランドカラー背景 + 白文字、secondary は現行の白背景 + ボーダー、danger は赤系とする

### 5.2 Diff viewer

- unified diff を行単位でパースし、行頭記号に応じて色分けする

| 行頭 | 表示 |
| --- | --- |
| `+` | 緑系背景 |
| `-` | 赤系背景 |
| `@@` | 青系テキスト（hunk ヘッダー） |
| その他 | 通常表示 |

- 外部ライブラリは追加せず、`diffText` の行頭記号による自前パースで実装する

### 5.3 Answer summary / Average score

- Analysis 画面に回答サマリを表示する: 回答数、平均スコア（`平均 X.X / 4 点` 形式）
- backend は `GET /api/patches/:patchId` のレスポンスに `answerSummary` を追加する

```json
{
  "answerSummary": {
    "answerCount": 5,
    "averageScore": 2.4,
    "maxScore": 12
  }
}
```

- `averageScore` は graded answer の `totalScore` の平均とし、graded answer が 0 件の場合は null とする

## 6. API 変更仕様

### 6.1 パス変更

backend のルートを MVP 仕様書に合わせて変更する。後方互換（旧パスの維持）は不要とする。

| Method | 変更前 | 変更後 |
| --- | --- | --- |
| GET | `/api/learn/:shareToken` | `/api/drills/:shareToken` |
| POST | `/api/learn/:shareToken/answers` | `/api/drills/:shareToken/answers` |
| GET | `/api/drill-runs/:drillRunId` | `/api/courses/:courseId/drill-runs/:drillRunId` |
| POST | `/api/drill-runs/:drillRunId/analysis` | `/api/courses/:courseId/drill-runs/:drillRunId/analyze` |

- ネスト化したルートでは、URL の `courseId` と対象リソースの `courseId` の一致を backend で検証し、不一致は 404 とする

### 6.2 レスポンス変更

- Drill 生成（`POST /api/courses/:courseId/drill-runs`）のレスポンスは MVP 仕様書 §8.4 に合わせ `{ "drillRunId": "...", "shareUrl": "/drills/:shareToken" }` とする
- 分析（`POST .../analyze`）のレスポンスは MVP 仕様書 §8.7 に合わせ `{ "patchId": "..." }` とする。遷移先の Analysis 画面が `GET /api/patches/:patchId` で詳細を取得する
- Drill Admin レスポンス（`GET /api/courses/:courseId/drill-runs/:drillRunId`）に `latestPatchId: string | null` を追加する
- Patch レスポンス（`GET /api/patches/:patchId`）に `answerSummary` を追加する（§5.3）
- `shareUrl` は `/drills/:shareToken` 形式に変更する

### 6.3 フィールド名変更

API レスポンスのフィールド名を MVP 仕様書に合わせる。frontend の型定義も追随する。

| 変更前 | 変更後 |
| --- | --- |
| `question.scenario` | `question.question` |
| `failureSignal.inferredCause` | `failureSignal.likelyCause` |
| `failureSignal.suspectedDocGap` | `failureSignal.suspectedDocumentGap` |

- Agent（ADK 側）の内部 schema は変更しない。差異がある場合は backend のレスポンス組み立て時にマッピングする

## 7. 実装順序

### Phase 1: Backend API 整合

- ルートのパス変更とネスト化（courseId 検証を含む）
- レスポンス変更（`latestPatchId`、`answerSummary`、`drillRunId`/`shareUrl`、`patchId`）
- フィールド名変更
- backend テストの更新

### Phase 2: ルーティング再設計

- ルート定義の変更と API client の追随
- Course Editor の URL パラメータからの講座ロード
- Generate drill / Analyze answers 後の遷移先変更
- Analysis 画面の patch 取得フロー変更

### Phase 3: 導線と UI

- アプリシェルとパンくず
- Latest drill / Latest patch / Share URL のリンク化とコピー機能
- ボタン階層、diff viewer 色分け、Answer summary / Average score 表示
- frontend テストの更新

## 8. 受け入れ条件

### 8.1 講座の再訪

Given 講座オーナーが講座を保存済みである
When `/courses/:courseId` を開く（またはリロードする）
Then 保存済みの title と markdown がフォームに表示される

### 8.2 新規作成から編集への遷移

Given 講座オーナーが `/courses/new` で講座を入力する
When Save を押す
Then URL が `/courses/:courseId` に置き換わり、以降の Save は更新として動作する

### 8.3 画面間導線

Given ドリルが生成済みである
When Course Editor の Latest drill リンクを押す
Then `/courses/:courseId/drill-runs/:drillRunId` に遷移する
And パンくずから Course Editor に戻れる

### 8.4 Share URL コピー

Given Drill Admin を表示している
When Copy ボタンを押す
Then 絶対 URL 形式の share URL がクリップボードにコピーされる

### 8.5 Analysis 表示

Given 分析が完了している
When `/courses/:courseId/drill-runs/:drillRunId/analysis` を開く
Then 最新 patch の diff が +/- 色分けで表示される
And 回答数と平均スコアが表示される

### 8.6 受講者 URL

Given 受講者が `/drills/:shareToken` を開く
When 3 問に回答して Submit する
Then 回答が保存され feedback が表示される
And オーナー向け導線は表示されない

## 9. スコープ外

- 講座一覧画面と一覧 API（`GET /api/courses`）
- Markdown preview（MVP 仕様書 §4.1 で任意とされている）
- 旧 URL / 旧 API パスからのリダイレクト（後方互換は不要）
- 認証・権限管理
- Agent（ADK 側）の schema 変更
