# Knowledge Drill 講座一覧 仕様書

Version: 0.1
Date: 2026-07-05
Base: `docs/frontend-navigation-ui-refresh-spec.md` v0.1（同仕様書 §9 でスコープ外とされた講座一覧を本仕様書で定義する）

## 1. 目的

現状、講座オーナーは保存済み講座の URL を自分で記憶していないと講座に戻れない。オーナーの入口となる講座一覧画面と、その裏付けとなる一覧 API を追加する。

一覧は単なるインデックスではなく「改善ループのダッシュボード」として設計する。各講座がループのどの段階にあるか（ドリル未生成 → ドリル配布中 → パッチ提案あり → 修正適用済み）を一覧上で可視化し、特にレビュー待ちパッチのある講座へオーナーを誘導する。

## 2. 現状の制約

- 一覧 API（`GET /api/courses`）が存在しない
- `CourseRepository` に全件取得メソッドがなく、`InMemoryFirestoreClient` にもコレクション全件列挙がない（`list_documents_by_field` のみ）
- `Course` モデルにタイムスタンプ（作成・更新日時）がない
- フロントのルートは `/` → `/courses`（新規エディタ）へのリダイレクトのみで、一覧の置き場所がない

## 3. API 仕様

### 3.1 `GET /api/courses`

講座一覧をサマリ形式で返す。認証はなし（MVP の既存方針に従う）。

```json
{
  "courses": [
    {
      "id": "course-9f3a",
      "title": "情報セキュリティ入門",
      "version": 3,
      "updatedAt": "2026-07-04T09:32:00Z",
      "drillStatus": "ready",
      "answerCount": 12,
      "patchStatus": "proposed",
      "latestDrillRunId": "drill-77e4",
      "latestPatchId": "patch-b2c1"
    }
  ]
}
```

- `markdown` 本文は含めない（一覧に不要、ペイロード削減）
- `drillStatus`: `latestDrillRunId` が null の場合は null。それ以外は最新 drill run の `status`
- `answerCount`: 最新 drill run への回答数。drill run がなければ 0
- `patchStatus`: `latestPatchId` が null の場合は null。それ以外は最新 patch の `status`
- 並び順は `updatedAt` の降順。`updatedAt` が null の講座は末尾
- ページネーションは行わない（MVP。§8 参照）

### 3.2 `Course` モデルへの `updatedAt` 追加

- `Course` に `updated_at: str | None = None`（ISO 8601 UTC）を追加する
- 講座の作成時・更新時に現在時刻を設定する
- 既存データに `updatedAt` がない場合は null として扱う（レスポンスでは `"updatedAt": null`）
- `CourseDetailResponse` にも同フィールドが含まれる（`Course` を継承しているため自動）

### 3.3 リポジトリ

- `InMemoryFirestoreClient` に `list_documents(collection)` を追加する
- `CourseRepository` に `list_all() -> list[Course]` を追加する
- サマリの組み立て（drill / patch / answer の参照）は service 層で行い、N 件の講座に対して drill run・patch・answer を講座単位で参照する（MVP のデータ量では十分）

## 4. ルーティング仕様

`frontend-navigation-ui-refresh-spec.md` §3.1 を次のとおり改訂する。

```text
/                        -> /courses へ redirect
/courses                 講座一覧（本仕様書で新設）
/courses/new             Course Editor（新規作成モード）
/courses/:courseId       Course Editor（編集モード）
（以下、既存仕様のまま）
```

- 現行の `/courses` は新規エディタだが、本仕様書適用後は一覧に割り当てる
- `:courseId` ルートとの衝突を避けるため、`new` は予約語となる（React Router では定義順で `/courses/new` を先に置く）

## 5. 画面仕様

### 5.1 レイアウト

- オーナー向けアプリシェル（ヘッダー）配下の 1 カラムページ
- ページヘッダー: 見出し「講座一覧」、主要アクション「＋ 新しい講座を作成」（primary ボタン、`/courses/new` へ遷移）
- 検索フィールド（講座名の部分一致、クライアントサイドフィルタ）と件数表示
- 講座リスト: 1 講座 = 1 行。行全体が `/courses/:courseId` へのリンク

### 5.2 行の表示内容

| 要素 | 内容 |
| --- | --- |
| タイトル | `title`（太字） |
| メタ行 | `v{version} · 更新 {updatedAt をローカル表示} · 回答 {answerCount} 件`。updatedAt が null なら省略、answerCount が 0 なら省略 |
| 状態チップ | §5.3 のロジックで最大 2 個 |

### 5.3 状態チップ

講座の「現在地」をチップで表現する。表示優先度順:

| 条件 | チップ | トーン |
| --- | --- | --- |
| `patchStatus == "proposed"` | パッチ提案あり | warning（最優先。レビュー待ちを目立たせる） |
| `patchStatus == "applied"` | 修正適用済み | accent |
| `drillStatus == "ready" / "analyzing" / "analyzed"` | ドリル配布中 | success |
| `drillStatus == "generating"` | ドリル生成中 | muted |
| `drillStatus == "failed"` | ドリル生成失敗 | error |
| `drillStatus == null` | ドリル未生成 | muted |

- パッチ系チップとドリル系チップは併記可（例: 「パッチ提案あり」+「ドリル配布中」）
- `patchStatus` が `rejected` / `stale` の場合、パッチ系チップは表示しない

### 5.4 状態別表示

| 状態 | 表示 |
| --- | --- |
| ロード中 | info バナー「講座を読み込んでいます。」 |
| 取得失敗 | error バナー（メッセージは API エラーに従う） |
| 0 件 | 空状態: 「まだ講座がありません。資料を登録して最初のドリルを作りましょう。」+ 作成ボタン |
| 検索 0 件 | 「『{query}』に一致する講座はありません。」 |

## 6. フロントエンド実装

- `api/types.ts` に `CourseSummary` / `CourseListResponse` を追加
- `api/client.ts` に `listCourses()` を追加
- `pages/CourseListPage.tsx` を新設（`pages/CourseListPage.test.tsx` を含む）
- `app/router.tsx` のルート変更（§4）
- Course Editor 側: 新規作成が `/courses/new` になることに伴い、既存の「`/courses` = 新規」前提のロジック・テストを更新する

## 7. 受け入れ条件

### 7.1 一覧表示

Given 講座が複数保存されている
When `/courses` を開く
Then 全講座がタイトル・バージョン・状態チップ付きで `updatedAt` 降順に表示される

### 7.2 講座への再訪

Given 講座一覧が表示されている
When 講座の行をクリックする
Then `/courses/:courseId` に遷移し、保存済みの内容がフォームに表示される

### 7.3 レビュー待ちの可視化

Given ある講座の最新パッチが `proposed` である
When `/courses` を開く
Then その講座に「パッチ提案あり」チップ（warning トーン）が表示される

### 7.4 新規作成導線

Given 講座一覧が表示されている
When 「新しい講座を作成」を押す
Then `/courses/new` に遷移し、空のエディタが表示される
And 保存すると `/courses/:courseId` に置き換わる（既存仕様 8.2 と同じ）

### 7.5 空状態

Given 講座が 1 件もない
When `/courses` を開く
Then 空状態メッセージと作成ボタンが表示される

## 8. スコープ外

- ページネーション・サーバーサイド検索（講座数が数百を超えるまで不要）
- 講座の削除・アーカイブ
- 並び替え UI（`updatedAt` 降順固定）
- 認証・オーナー別のフィルタリング
- ドリル実行履歴の一覧（最新 drill run のみ扱う）
