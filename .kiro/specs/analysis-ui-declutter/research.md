# Research & Design Decisions — analysis-ui-declutter

## Summary
- **Feature**: `analysis-ui-declutter`
- **Discovery Scope**: Extension(既存 frontend の UI 再構成。API / backend / agent 変更なし)
- **Key Findings**:
  - ドリル確認(`DrillAdminPage`)は 1 カラム縦積みで、stat 行・採点状況・タイムライン・共有 URL・設問詳細・回答一覧が同じ強さで並ぶ。講座管理(`CourseEditorPage`)は既に main + サイドの 2 カラム(`.editor-grid`)であり、同じ文法を再利用できる
  - `DocumentPatch` API 応答には検証エージェントの結果を示すフィールドが存在しない。検証チェック表示は requirements 段階でスコープ外に確定済み
  - パッチレビューの講座バージョン表示は、既存 `api.getCourse` の並行取得で実現できる(API 変更不要)。diff の追加/削除行数は `diffText` の行頭記号から純粋関数で算出できる

## Research Log

### 既存レイアウトパターンと再利用可能な CSS
- **Context**: R1(2 カラム化)を既存の視覚言語(R7.3)で実現する方法の確認
- **Sources Consulted**: `frontend/src/app/App.css`(`.editor-grid` L405、`.stat-row` L586、`.q-card` L677、`.meta-chips` L988、`.patch-grid` L1002、`.analysis-timeline` L1015、狭幅フォールバック L1476-1480)、`CourseEditorPage.tsx`
- **Findings**:
  - `.editor-grid` + `.editor-side` が main + サイド 2 カラムの既存実装。狭幅では 1 カラムに折り返す media query も既存
  - 講座管理のサイドは `side-list`(dt/dd)形式の「講座の状態」カードを持ち、ドリル確認の状態表示にそのまま流用できる
  - `.stat-row` はドリル確認のみが使用。削除しても他画面に影響しない
- **Implications**: 新規レイアウトシステムは作らず、`.editor-grid` 系クラスの再利用+ドリル確認固有の差分クラス追加に留める

### AnalysisTimeline の現状と拡張点
- **Context**: R3(実行状態表示)・R6.1(evidence 折りたたみ)を単一コンポーネントで両画面に提供する方法
- **Sources Consulted**: `frontend/src/components/common/AnalysisTimeline.tsx`、`backend/app/services/analysis_service.py`(ANALYSIS_STEPS、`_update_timeline`)
- **Findings**:
  - `AnalysisTimelineItemView` は `status`(pending/running/completed/failed/skipped)・`summary`・`evidence[]`・`completedAt` を既に持つ。実行状態アイコンに必要なデータは揃っている
  - `completedAt` はステップ完了時のみ非 null。分析開始時刻は応答に含まれないため、先頭ステップの所要時間は算出できない。連続する完了ステップ間の差分は算出可能
  - DrillAdminPage は 1 秒ポーリングで `getDrill` を再取得し timeline を更新済み(既存機構、R7.4)
  - 表示バリエーション(evidence 常時表示 / 折りたたみ)は利用画面で要件が異なる(ドリル確認=分析の見せ場として展開、パッチレビュー=判断ログとして summary 中心)
- **Implications**: AnalysisTimeline に表示バリエーション prop を追加し、両画面の要件差を props で吸収する。ポーリング機構・データ shape は変更しない

### パッチレビューの diff メタ情報のデータ源
- **Context**: R5(バージョン表記・追加/削除行数)を frontend のみで実現できるか
- **Sources Consulted**: `frontend/src/api/types.ts`(`DocumentPatch`)、`frontend/src/pages/PatchReviewPage.tsx`、`CourseEditorPage.tsx` の course 取得
- **Findings**:
  - `DocumentPatch` は `diffText` / `baseMarkdown` / `patchedMarkdown` を持つが、講座バージョンを持たない
  - 講座バージョンは `api.getCourse(patch.courseId)` の応答(`Course.version`)から取得できる。proposed パッチの適用後バージョンは `version + 1` として表示できる(stale は既存バナーが担当)
  - 追加/削除行数は unified diff の行頭 `+` / `-`(ヘッダ行 `+++` / `---` を除外)の集計で得られる
- **Implications**: PatchReviewPage に course の後追い取得を追加する。getPatch 解決で即 ready 表示し、getCourse は独立 state で非ブロッキングに取得する(未解決・失敗時はバージョン表記のみ省略、R5.3。design review 指摘 3 で明確化)。行数集計は `lib/` の純粋関数にして単体テストする(frontend skill のテスト方針に従う)

### 既存テスト・e2e への影響
- **Context**: UI 再構成が既存テストのどの assertion を壊すか
- **Sources Consulted**: `DrillAdminPage.test.tsx`、`PatchReviewPage.test.tsx`、`AnalysisTimeline.test.tsx`、`e2e/knowledge-drill.spec.ts`
- **Findings**:
  - e2e が `リスクノート` の可視性を assert している(L122)。R6.4 でリスクノートは独立カードでなくなるため更新が必要
  - PatchReviewPage.test は `分析タイムライン` 見出しと status 遷移を assert。タイムライン構造変更後も見出しは維持されるが、evidence 折りたたみの初期状態テストを追加する
  - DrillAdminPage.test は stat 行のラベルに依存する assertion があれば更新が必要(構造変更の影響範囲)
- **Implications**: Testing Strategy に既存 assertion の更新箇所を明記する

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| 既存 editor-grid 文法の再利用(採用) | 講座管理と同じ main + サイド 2 カラムにドリル確認を揃える | 一貫性、CSS 追加最小、狭幅フォールバック既存 | サイド幅 320px に採点状況が収まるかの確認が必要 | R1.1 が明示的に「講座管理と同じ構成」を要求 |
| 新規レイアウトコンポーネント導入 | 汎用 TwoColumnLayout component を作る | 将来の再利用 | 過剰設計。利用箇所 2 つに対して抽象が早すぎる | frontend skill の「浅い構造優先」に反するため不採用 |
| タブ切り替えで情報を分割 | 設問 / 回答 / 分析をタブ化 | 1 画面の情報量最小 | ライフサイクルの主役が隠れる。動画で切り替え操作が入る | 撮影要件(1 画面で流れが映る)に反するため不採用 |

## Design Decisions

### Decision: AnalysisTimeline は単一コンポーネント + 表示 props で両画面に対応する
- **Context**: ドリル確認(R3: 実行の見せ場)とパッチレビュー(R6.1: summary 中心の判断ログ)で evidence の扱いが異なる
- **Alternatives Considered**:
  1. 画面ごとに別コンポーネント(LiveTimeline / LogTimeline)を作る
  2. 単一コンポーネントに `evidenceDisplay: 'expanded' | 'collapsed'` prop を追加する
- **Selected Approach**: 2。既存 `AnalysisTimeline` に表示 prop を追加し、フェーズグループ化・status 表現は共通のまま維持する
- **Rationale**: データ shape・グループ化ロジックは完全に共通で、差分は evidence の初期表示のみ。分割は重複を生む
- **Trade-offs**: props が 1 つ増えるが、コンポーネント数と重複を抑えられる
- **Follow-up**: 折りたたみは `<details>` で実装し、キーボード操作(R2.4 と同型)を担保する

### Decision: ステップ所要時間は「連続する完了ステップ間の差分」のみ表示する
- **Context**: R3.6 は完了時刻または経過時間の表示を Where 条件で要求。分析開始時刻は API 応答に存在しない
- **Alternatives Considered**:
  1. backend に開始時刻を追加する(API 変更)
  2. 先頭ステップは表示なし、2 番目以降は直前ステップの completedAt との差分を表示
  3. すべて completedAt の時刻(HH:MM:SS)を表示
- **Selected Approach**: 2(算出できないものは表示しない)
- **Rationale**: API 変更禁止(R7.2)の制約下で、嘘のない値だけを出す。時刻表示(案 3)は撮影時に情報量が増える割に判断材料にならない
- **Trade-offs**: 先頭ステップに所要時間が出ない
- **Follow-up**: completedAt が null のままのステップ(failed 時)は差分計算をスキップする

### Decision: リスクノートは FailureSignal カード側に統合し、独立カードを廃止する
- **Context**: R6.4。riskNotes はパッチ単位、failureSignals は所見単位でデータ粒度が異なる
- **Alternatives Considered**:
  1. 各 FailureSignal カードに riskNotes を複製表示
  2. FailureSignal カード群の末尾に「リスクと注意点」行ブロックとして 1 回だけ表示
- **Selected Approach**: 2。根拠カラム(左)の最後に riskNotes を 1 回表示し、独立した `card` としては出さない
- **Rationale**: riskNotes はパッチ全体の注意点なので複製は誤読を生む。表示位置を根拠カラムに寄せることで「根拠は左、変更は右」の役割分担を守る
- **Trade-offs**: e2e の `リスクノート` assertion の更新が必要
- **Follow-up**: riskNotes が空配列の場合はブロックごと省略する

### Decision: 分析実行中のフォーカスは「閉じた details への切り替え」で実現する(design review で改訂)
- **Context**: R4.1 は設問・回答一覧の「折りたたみ」を要求している。初版 design は「描画しない」を選択したが、design review で requirements との不一致(NO-GO 指摘 2)が確認された
- **Alternatives Considered**:
  1. 分析開始時に設問・回答セクションを `<details>` の閉状態に切り替える(手動再展開可)
  2. 分析中は設問・回答セクションを描画しない(初版の選択。requirements の「折りたたみ」と不一致)
  3. requirements を「非表示」に改訂して再承認する
- **Selected Approach**: 1。page state で `<details>` の open を制御し、分析開始で閉、分析失敗で自動再展開。オーナーは分析中も手動で開ける
- **Rationale**: 承認済み requirements の文言(折りたたみ・再び閲覧可能)に正確に一致し、再承認が不要。分析中に設問を確認したいケースも失わない
- **Trade-offs**: 「勝手に閉じる」体験になるが、分析開始は明示的なユーザー操作直後であり文脈が明確
- **Follow-up**: 閉→手動再展開(R4.1)、失敗時の自動復元(R4.2)をテストで担保する

### Decision: 2 カラムの順序は DOM 順(side 先)+ grid-template-areas で保証する(design review で追加)
- **Context**: R1.2(狭幅で共有 URL と状態を主内容より先に表示)。既存 `.editor-grid` の media query は 1 カラム化するだけで順序を変えないため、再利用だけでは満たせない(NO-GO 指摘 1)
- **Alternatives Considered**:
  1. DOM は main 先のまま、狭幅 media query で CSS `order` によりサイドを先へ移動
  2. DOM をサイド先にし、広幅は `grid-template-areas: "main side"` で main を左に配置、狭幅は素の DOM 順で 1 カラム表示
- **Selected Approach**: 2(`.drill-grid` を新設)
- **Rationale**: CSS `order` は視覚順と DOM 順(キーボード・支援技術の読み順)の乖離を生む。DOM 順をサイド先に固定すれば、狭幅・支援技術の両方で共有 URL が先になり R1.2/R1.3 と整合する
- **Trade-offs**: 広幅の視覚順(左 main)と DOM 順が乖離するが、「共有 URL を先に読ませる」意図と一致するため許容
- **Follow-up**: DOM 順のテスト(サイドが設問一覧より先に存在)と、モバイル幅の目視確認を完了前チェックに含める

### Decision: diff 行数集計は `lib/` の純粋関数にする
- **Context**: R5.1。分岐を持つ文字列処理であり、frontend skill は branching validation を lib/ に置くことを要求
- **Selected Approach**: `lib/diffStats.ts` に `countDiffLines(diffText: string): { added: number; removed: number }` を追加し、`+++` / `---` ヘッダ行を除外して集計する
- **Rationale**: React なしで直接テストできる。DiffViewer は表示のみに専念する
- **Trade-offs**: なし(ファイル 1 つ追加)
- **Follow-up**: 空 diff・ヘッダのみ diff のエッジケースをテストする

## Risks & Mitigations
- サイド幅(約 300-320px)に設問別採点状況が収まらない → 欠落タグは折り返し表示、長文タグは既存の chip 折り返しスタイルを流用。モバイル幅の確認を完了前チェックに含める(R1.2)
- 分析中の主カラム切り替えでレイアウトシフトが起きる → タイムラインカードを主カラム先頭に固定配置し、切り替えはカード単位で行う
- e2e assertion(リスクノート等)の破損 → Testing Strategy に更新対象を明記し、実装タスクに含める
- prefers-reduced-motion 環境でスピナーが残る → CSS media query で animation を無効化し、静的アイコンに差し替える(R3.7)

## References
- `.kiro/specs/analysis-ui-declutter/requirements.md` — 本設計の入力
- `.kiro/specs/score-progression-ui/requirements.md` — 隣接 spec(講座管理サイドのスコア推移カード)
- `docs/hackathon-feedback-loop-feature-design.md` §9.1 — 画面分担(Drill Admin に Before/After を置かない)
- `.agents/skills/frontend/SKILL.md` — 依存方向・テスト方針・完了前チェック
