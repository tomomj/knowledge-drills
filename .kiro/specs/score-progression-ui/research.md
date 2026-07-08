# Research & Design Decisions

## Summary

- **Feature**: `score-progression-ui`
- **Discovery Scope**: Extension
- **Key Findings**:
  - `CourseMetricsResponse` / `CourseMetricsRun` と `api.getCourseMetrics(courseId)` は既に frontend に存在し、backend/API 契約変更は不要である。
  - Course Editor は metrics 取得失敗を `null` に落として編集画面を継続表示する helper を持つため、この degrade 方針を Course History にも揃える。
  - `CourseMetricsRun` には時系列 field がないため、同一 version の複数 run は「metrics 応答内で後に現れる run」を採用し、時系列上の最新とは扱わない。

## Research Log

### Course Editor metrics 表示の拡張点

- **Context**: Before / After が最初と最後の scored run だけを表示しており、中間 version が消える。
- **Sources Consulted**:
  - `frontend/src/pages/CourseEditorPage.tsx`
  - `frontend/src/pages/CourseEditorPage.test.tsx`
  - `frontend/src/app/App.css`
- **Findings**:
  - `buildMetricsComparison` は metrics run を index 付きで sort し、同一 version では元順序を維持している。
  - `loadCourseMetrics` は metrics 取得失敗を catch して `null` を返す。
  - `MetricsComparisonCard` は `aria-label="改善メトリクス"` を持ち、既存テストもこの label を使っている。
- **Implications**:
  - sort/filter の既存挙動を保ったまま、返却値を全 scored run の progression に変える。
  - metrics 取得失敗時の degrade は既存 helper を維持し、カード非表示で表現する。
  - accessibility contract とテスト安定性のため、カードの accessible name は維持する。

### Course History metrics 接続点

- **Context**: 更新履歴画面で diff と version 別平均点を同じ画面に表示する。
- **Sources Consulted**:
  - `frontend/src/pages/CourseHistoryPage.tsx`
  - `frontend/src/pages/CourseHistoryPage.test.tsx`
  - `frontend/src/api/client.ts`
  - `frontend/src/api/types.ts`
- **Findings**:
  - Course History は現在 revisions だけを読み、selectedVersion に応じて diff を別 effect で読む。
  - `api.getCourseMetrics` は既に利用可能で、mock 追加だけで page test を拡張できる。
  - `CourseMetricsRun` には `createdAt` や採点完了時刻がない。
- **Implications**:
  - revisions load と同じ effect 内で metrics を並行取得する。
  - metrics 取得だけ失敗しても revisions/diff は表示し、平均点 meta だけ省略する。
  - version score map は response order の最後を採用し、時系列の最新性を推測しない。

### CSS と responsive 表示

- **Context**: スコア推移カードに sparkline と複数 run の flow 表示を追加する。
- **Sources Consulted**:
  - `frontend/src/app/App.css`
  - `docs/score-progression-ui-spec.md`
  - `.agents/skills/frontend/SKILL.md`
- **Findings**:
  - 既存 `.metrics-card__body` は 2 カラム grid で、progression には sparkline + flow の縦積みが必要になる。
  - `.select-row__meta` は `white-space: nowrap` で、平均点追加後も短い meta 表示なら CSS 変更は不要。
  - frontend 規約は浅い構成と page-level state を優先し、新規 global state や重い構造を避ける。
- **Implications**:
  - スコア推移は `CourseEditorPage.tsx` 内の小さな表示部品と helper に留める。
  - CSS は `.metrics-card__body` の縦積み化と flow/sparkline の追加に限定する。
  - Course History は既存 meta 表示の文字列合成のみで対応する。

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Page-local extension | 既存 page 内に helper と表示部品を追加する | 最小変更、既存 test と依存方向を維持 | helper の再利用性は限定的 | 採用。対象が 2 page の owner UI に閉じているため十分 |
| Shared component 化 | `components/` に score progression component を新設する | 将来の再利用に向く | 現時点では抽象化が先行しやすい | 不採用。Drill Admin 追加は out of scope |
| Chart library 導入 | 外部 chart package で sparkline を描く | 表現力が高い | 依存追加、bundle 増、仕様に対して過剰 | 不採用。SVG で十分 |

## Design Decisions

### Decision: 差分・tone・折れ線をスコア率基準に統一する

- **Context**: `maxScore` が run ごとに異なると raw 点差と正規化された折れ線が逆方向になり得る。
- **Alternatives Considered**:
  1. Raw 点差を維持し、折れ線だけ比率にする。
  2. Raw 点数表示は維持し、差分・tone・折れ線をスコア率に揃える。
- **Selected Approach**: `averageScore / maxScore` をスコア率として扱い、区間差分・総差分・chip tone・sparkline をすべてパーセントポイント基準にする。
- **Rationale**: owner が見る改善/悪化の方向が UI 内で矛盾しない。
- **Trade-offs**: 既存の `+1.0 点` 表示から `+25.0 pp` 表示に変わるため、テストと文言を更新する必要がある。
- **Follow-up**: `maxScore <= 0` はスコア率を定義できないため、UI 表示対象から除外する defensive guard を実装時に入れる。

### Decision: Course History は response order を正とし、時系列最新を推測しない

- **Context**: metrics API に run 作成時刻や採点時刻がない。
- **Alternatives Considered**:
  1. 同一 version の最後の run を「最新」と呼ぶ。
  2. API 応答内で後に現れる run とだけ定義する。
  3. backend/API に時系列 field を追加する。
- **Selected Approach**: Course History の version score map は response order の最後を採用し、最新性は主張しない。
- **Rationale**: backend/API 変更を out of scope にしたまま、決定的でテスト可能な表示にできる。
- **Trade-offs**: 実際の最新 run とは限らないが、現契約内で誤った意味づけを避けられる。
- **Follow-up**: 将来 API に `createdAt` 等が追加された場合は revalidation する。

### Decision: 新規 dependency と shared component を追加しない

- **Context**: sparkline は装飾的で、要求範囲は owner 向け 2 page に限定される。
- **Alternatives Considered**:
  1. Chart library を追加する。
  2. `components/` に reusable chart component を作る。
  3. `CourseEditorPage.tsx` 内に `ScoreSparkline` を置く。
- **Selected Approach**: `ScoreSparkline` と score progression helper を `CourseEditorPage.tsx` 内に置く。
- **Rationale**: frontend skill の浅い構成、依存追加なし、ページ局所性に合う。
- **Trade-offs**: 他画面で再利用するときは後で component 化が必要。
- **Follow-up**: Drill Admin 等へ展開する場合のみ抽出を検討する。

## Risks & Mitigations

- スコア率デルタの `pp` 表示が既存 `点` 表示から変わる - テストで `pp` 表記と raw 点数表示が同居することを明示する。
- sparkline の SVG が狭い幅で潰れる - CSS で高さを固定し、flow は `flex-wrap` で折り返す。
- metrics 取得失敗が history 全体の failure に伝播する - `loadCourseMetrics` helper を Course History 側にも置き、metrics だけ `null` に落とす。
- learner view への混入 - 変更ファイルを owner page に限定し、learner route/API 型は触らない。

## References

- `docs/score-progression-ui-spec.md` - 背景資料。実装仕様の正は本 spec ディレクトリ。
- `.agents/skills/frontend/SKILL.md` - frontend 構成、依存方向、完了前チェック。
- `frontend/src/pages/CourseEditorPage.tsx` - 既存 metrics comparison と metrics degrade helper。
- `frontend/src/pages/CourseHistoryPage.tsx` - version list と diff 表示。
