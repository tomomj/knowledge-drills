# Requirements Document

## Introduction

Score Progression UI は、講座オーナーが教材改善ループを複数回まわしたときに、
Course Editor と Course History 上で version ごとの平均点推移を確認できるようにする
owner 向けフロントエンド改善である。

現状の Course Editor は、採点済み run の最初と最後だけを Before / After として表示するため、
v1 -> v2 -> v3 のような中間改善が UI から消える。既存の
`GET /api/courses/{courseId}/metrics` は全 run の version・平均点・満点・回答数を返しているため、
本機能は backend/API の契約を変更せず、既存メトリクスを UI で推移として表現する。
本 spec での「スコア率」は `averageScore / maxScore` を 0-100% の割合として扱う指標であり、
差分・tone・折れ線はこのスコア率基準で揃える。各 run の点数表記は既存どおり
平均点と満点の raw 値を表示する。

`docs/score-progression-ui-spec.md` は本 spec の入力となった背景資料である。
実装仕様の正は本 requirements とし、承認後は同じ spec ディレクトリの design/tasks を含める。

## Boundary Context

- **In scope**: Course Editor の改善メトリクス表示を「スコアの推移」へ拡張すること、採点済み run 全件の version・平均点・回答数・区間スコア率差分・総スコア率差分を owner に表示すること、Course History の version 一覧へ version 別平均点を添えること、metrics 取得失敗時に編集画面と履歴表示を壊さないこと。
- **Out of scope**: backend/API 契約変更、metrics 集計ロジック変更、グラフライブラリ追加、講座の状態カード内の「最新パッチ」リンク削除または置換、受講者向け画面へのメトリクス表示、Drill Admin への Before / After 追加。
- **Adjacent expectations**: `hackathon-feedback-loop` spec で導入済みの metrics API と owner ページ構成に依存する。Course Editor の「最新パッチ」導線は patch review への常設導線として維持し、スコア推移は改善効果の証拠として別役割で表示する。

## Requirements

### Requirement 1: Course Editor でスコア推移を表示する

**Objective:** As a 講座オーナー, I want 複数 version の平均点推移を Course Editor で確認できる, so that 教材改善の効果と中間ステップを失わずに判断できる

#### Acceptance Criteria

1. When オーナーが Course Editor を開き、採点済み run が 2 件以上存在する, the Knowledge Drills frontend shall `スコアの推移` カードを owner 向け講座管理画面に表示する
2. When メトリクスに回答数が 1 件以上かつ平均点・満点が計測済みの run が含まれる, the Knowledge Drills frontend shall その run をスコア推移の表示対象に含める
3. If 回答数が 0 件、または平均点・満点が未計測の run が含まれる, the Knowledge Drills frontend shall その run をスコア推移の表示対象から除外する
4. When スコア推移の表示対象 run を並べる, the Knowledge Drills frontend shall course version 昇順で表示し、同一 version 内では metrics 応答内の順序を維持する
5. When 表示対象 run が 2 件未満である, the Knowledge Drills frontend shall `スコアの推移` カードを表示しない
6. When スコア推移カードが表示される, the Knowledge Drills frontend shall 各 run の version、平均点、満点、回答数を表示する
7. When 連続する 2 つの表示対象 run が存在する, the Knowledge Drills frontend shall run 間のスコア率差分を符号付き 1 桁小数のパーセントポイントで表示する
8. When 最初と最後の表示対象 run が存在する, the Knowledge Drills frontend shall 総スコア率差分をカード見出しの chip として符号付き 1 桁小数のパーセントポイントで表示する
9. If 総スコア率差分が 0 以上である, the Knowledge Drills frontend shall 総差分 chip を成功 tone で表示する
10. If 総スコア率差分が 0 未満である, the Knowledge Drills frontend shall 総差分 chip を警告 tone で表示する
11. If Course Editor で講座メトリクスの取得に失敗する, the Knowledge Drills frontend shall 講座編集画面を継続表示し、スコア推移カードだけを省略する

### Requirement 2: 推移の視覚表現をアクセシブルに提供する

**Objective:** As a 講座オーナー, I want 平均点の上がり下がりを一目で確認できる, so that デモやレビュー時に改善傾向をすばやく説明できる

#### Acceptance Criteria

1. When スコア推移カードが表示される, the Knowledge Drills frontend shall version ごとのスコア率推移をコンパクトな折れ線表示として提示する
2. When run ごとに満点が異なる, the Knowledge Drills frontend shall 各 run の平均点をその run の満点に対する比率として扱い、差分・tone・折れ線を同じスコア率基準で表示する
3. When スコア推移カードが表示される, the Knowledge Drills frontend shall カードのアクセシブルな名前として `改善メトリクス` を維持する
4. When 支援技術が推移の視覚表現を参照する, the Knowledge Drills frontend shall `バージョンごとのスコア率の推移` を意味する代替ラベルを提供する
5. Where 画面幅が狭い表示環境である, the Knowledge Drills frontend shall version ごとのスコア表示と差分表示を折り返し、テキストの重なりや判読不能な切れを起こさない

### Requirement 3: Course History の version 一覧に平均点を添える

**Objective:** As a 講座オーナー, I want 更新履歴の各 version に平均点が表示される, so that diff とスコア変化を同じ画面で関連付けて確認できる

#### Acceptance Criteria

1. When オーナーが Course History を開く, the Knowledge Drills frontend shall 更新履歴の取得と並行して講座メトリクスを取得する
2. When 更新履歴の version に採点済み run が存在する, the Knowledge Drills frontend shall その version 行の meta 表示に `平均 X.X / N 点` を含める
3. When 同一 version に複数の採点済み run が存在する, the Knowledge Drills frontend shall metrics 応答内で後に現れる run の平均点と満点をその version の表示値として扱い、時系列上の最新 run であるとは推測しない
4. When 更新履歴の version に採点済み run が存在しない, the Knowledge Drills frontend shall その version 行に平均点を表示せず、既存の日時表示を維持する
5. When version 行に平均点と日時の両方が存在する, the Knowledge Drills frontend shall 平均点と日時を ` · ` 区切りで表示する
6. If 講座メトリクスの取得に失敗する, the Knowledge Drills frontend shall 更新履歴一覧と diff 表示を継続し、平均点だけを省略する

### Requirement 4: 既存 owner 導線と learner 境界を維持する

**Objective:** As a 講座オーナー, I want スコア推移と patch review 導線が両方維持される, so that 改善効果の証拠確認と修正案レビューを迷わず行える

#### Acceptance Criteria

1. The Knowledge Drills frontend shall Course Editor の講座状態カードにある version、更新履歴、最新ドリル、最新パッチの表示役割を維持する
2. The Knowledge Drills frontend shall `最新パッチ` リンクを削除、置換、またはスコア推移カードへ統合しない
3. The Knowledge Drills frontend shall スコア推移表示を owner 向け Course Editor と Course History に限定する
4. The Knowledge Drills frontend shall 受講者向け画面に平均点推移、version 別平均点、差分 chip を表示しない
5. The Knowledge Drills frontend shall backend/API のメトリクス応答 shape が現状どおりであることを前提に表示を行い、API 変更を要求しない
