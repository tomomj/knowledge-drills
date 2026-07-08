# スコア推移表示 UI 設計

Status: Draft v0.1（2026-07-08）
Scope: Course Editor のスコア推移カード、Course History のバージョン別平均点表示

## 1. 背景と課題

ハッカソン戦略（`hackathon-strategy.md`）の最重要ショットは「スコアが上がるグラフ」だが、
現状の UI は改善ループを 2 周以上回したときの推移を表現できない。

- Course Editor の `MetricsComparisonCard` は scored run の**最初と最後だけ**を
  Before / After の 2 カラムに潰しており、v1 → v2 → v3 と回すと中間の v2 が UI から消える
- `GET /api/courses/{courseId}/metrics` の `runs` は既に全 run の
  `courseVersion` / `averageScore` / `maxScore` / `answerCount` を返しており、
  データは揃っている。ボトルネックはフロントエンドの表示だけ
- 「最新パッチ」リンク（講座の状態カード）は Patch Review への常設導線であり**削除しない**。
  導線（最新パッチ）と証拠（スコア推移）は役割が別

## 2. 方針

- backend / API は変更しない。フロントエンドのみの改修
- 変更 1: Course Editor の Before / After カードを「スコアの推移」カードに拡張する（本命）
- 変更 2: Course History のバージョン一覧に平均点を添える（次点）
- 「講座の状態」カード（バージョン / 更新履歴 / 最新ドリル / 最新パッチ）は現状維持

## 3. 変更 1: Course Editor「スコアの推移」カード

### 3.1 表示イメージ

```text
スコアの推移                        [+1.7 点]
（SVG スパークライン: 点と折れ線）
v1 2.1 / 4 点   +1.3 →  v2 3.4 / 4 点   +0.4 →  v3 3.8 / 4 点
回答 4 件                回答 4 件                回答 5 件
```

- カード見出しを `Before / After` から `スコアの推移` に変更
- 右上 chip は総デルタ（最後 − 最初）。正なら `chip--success`、負なら `chip--warning`
- scored run（`answerCount > 0` かつ `averageScore` / `maxScore` が非 null）**全件**を
  `courseVersion` 昇順（同一 version は元の配列順）に横並び表示
- 各ステップ間に区間デルタ（`+1.3 →`）を挟む
- scored run が 2 件未満のときは現行同様カード自体を表示しない
- scored run が 2 件のときは実質現行の Before / After と同じ見え方に退化する

### 3.2 実装

`frontend/src/pages/CourseEditorPage.tsx` のみ変更。

- `MetricsComparison` 型（`before` / `after` / `delta`）を
  `ScoreProgression` 型（`runs: ScoredMetricsRun[]` / `totalDelta: number`）に置換
- `buildMetricsComparison` を `buildScoreProgression` に置換。
  filter / sort ロジックは現行を流用し、最初と最後の抽出をやめて全件返す
- `MetricsComparisonCard` / `MetricRunColumn` を `ScoreProgressionCard` に置換
  - `aria-label="改善メトリクス"` は維持
  - 各 run のスコア表記は現行フォーマット `{score.toFixed(1)} / {maxScore} 点`、
    `回答 {answerCount} 件` を維持
- `ScoreSparkline` component を同ファイル内に追加（ライブラリ不使用、装飾目的）
  - `viewBox="0 0 240 56"`、`preserveAspectRatio="none"`、幅 100%
  - y 座標は `averageScore / maxScore` の比率で正規化
    （run ごとに `maxScore` が異なっても破綻しない）
  - `polyline` + 各点 `circle`。色は CSS の `currentColor`（`var(--accent)`）
  - `role="img"` + `aria-label="バージョンごとの平均点の推移"`

### 3.3 CSS（`frontend/src/app/App.css`）

- `.metrics-card__body` を 2 カラム grid から縦積み grid（sparkline + flow）に変更
- 追加クラス:
  - `.metrics-sparkline`: `width: 100%; height: 56px; color: var(--accent);`
  - `.metrics-flow`: `display: flex; flex-wrap: wrap; align-items: center;`
    `list-style: none; margin: 0; padding: 0;`
  - `.metrics-flow__step`: `display: flex; align-items: center; gap: 10px;`
  - `.metrics-flow__delta`: 小さめ・`var(--ink-3)`・`tabular-nums`
- `.metrics-card__run` / `.metrics-card__label` は流用

## 4. 変更 2: Course History のバージョン別平均点

### 4.1 表示イメージ

バージョン一覧の各行の meta 部分に平均点を合成する。

```text
v3    平均 3.8 / 4 点 · 2026/07/05 18:00
v2    平均 3.4 / 4 点 · 2026/07/04 18:00
v1    平均 2.1 / 4 点 · 2026/07/03 18:00
```

- 「このパッチ（diff）→ このスコア上昇」が同一画面で結線され、
  DevOps メタファーの「SLO 改善の確認」に対応する
- scored run がないバージョンは日時のみ表示（現行表示）

### 4.2 実装

`frontend/src/pages/CourseHistoryPage.tsx` のみ変更。

- revisions 取得と並行して `api.getCourseMetrics(courseId)` を `Promise.all` で取得
- metrics 取得失敗は履歴表示を壊さない（catch して `null`。
  Course Editor の `loadCourseMetrics` と同じ扱い）
- `courseVersion -> { averageScore, maxScore }` の Map を組み立てる。
  同一 version に複数の scored run がある場合は**後の run（最新）で上書き**
- `select-row__meta` の文字列を
  `[平均 X.X / N 点, 日時].filter(Boolean).join(' · ')` で合成する（CSS 変更不要）

## 5. テスト方針

### CourseEditorPage.test.tsx

- 既存「shows before after metrics」を「スコアの推移」表示に更新
  （タイトル文言、v1 / v2、`2.5 / 4 点`、`+1.0 点` は継続して検証）
- 追加: scored run 3 件（v1 2.1 → v2 3.4 → v3 3.8）で
  全バージョン・区間デルタ（`+1.3` / `+0.4`）・総デルタ（`+1.7 点`）が表示される
- 追加: 未採点 run（`answerCount: 0`）は推移から除外される
- 既存「hides」テストは文言だけ `スコアの推移` に更新

### CourseHistoryPage.test.tsx

- `getCourseMetrics` mock を追加（default: `runs: []`）
- 追加: scored run のあるバージョン行に `平均 X.X / N 点` が表示される
- 追加: scored run のないバージョン行には平均点が表示されない
- 追加: metrics 取得失敗でも履歴と diff は表示される

## 6. 完了前チェック

frontend skill の完了前チェックに従う。

- `npm run typecheck` / `npm run lint`
- 変更 page のテスト実行（vitest）
- learner view への影響なし（owner ページのみの変更）を確認
- モバイル幅で `.metrics-flow` の折り返しが破綻しないことを確認

## 7. やらないこと

- backend / API の変更（metrics API は現状のまま）
- 「最新パッチ」リンクの削除・置き換え
- グラフライブラリの導入（SVG 手書きで十分。戦略 doc「折れ線グラフ1本でいい。凝らない」）
- Drill Admin への Before / After 追加（`hackathon-feedback-loop-feature-design.md` §9.1 の
  画面分担を維持する）
