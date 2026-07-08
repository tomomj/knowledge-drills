# Implementation Plan

- [x] 1. Owner page implementation
- [x] 1.1 Course Editor のメトリクスをスコア推移として導出する
  - 採点済み run の判定を回答あり・平均点あり・満点あり・満点が正の値で揃える
  - 表示対象 run を course version 昇順、同一 version は metrics 応答順で並べる
  - 表示対象が 2 件未満なら推移 state を作らず、カード非表示のままにする
  - 区間差分と総差分をスコア率のパーセントポイントで導出し、raw 点差を改善判定に使わない
  - metrics 取得失敗時も講座編集フォームが表示され、推移カードだけが出ない状態になる
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 1.9, 1.10, 1.11, 2.2_

- [x] 1.2 Course Editor にスコア推移カードと折れ線表示を追加する
  - 見出しを `スコアの推移` に変更し、カードの accessible name は `改善メトリクス` を維持する
  - 各 run に version、raw 平均点、満点、回答数を表示する
  - 各 run 間に区間スコア率差分を表示し、総スコア率差分 chip を success/warning tone で表示する
  - スコア率推移の折れ線に支援技術向けの代替ラベルを付ける
  - 講座状態カードの version、更新履歴、最新ドリル、最新パッチの導線が従来どおり表示される
  - _Requirements: 1.1, 1.6, 1.7, 1.8, 1.9, 1.10, 2.1, 2.2, 2.3, 2.4, 4.1, 4.2_

- [x] 1.3 (P) Course History の version 行へ平均点 meta を追加する
  - 更新履歴と講座メトリクスを並行して読み、更新履歴の取得失敗と metrics 取得失敗を分離する
  - metrics 取得失敗時は version 一覧と diff 表示を継続し、平均点だけを省略する
  - 採点済み run がある version には `平均 X.X / N 点` を日時と合わせて表示する
  - 平均点・満点が未計測、回答 0 件、または満点が正でない run は version score map から除外する
  - 同一 version に複数の採点済み run がある場合は metrics 応答順で後に現れる run を採用し、時系列上の最新とは扱わない
  - 採点済み run がない version は従来どおり日時のみ、または日時がない場合は既存の空表示を維持する
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - _Boundary: CourseHistoryVersionScores_

- [x] 1.4 Metrics card の responsive styling を更新する
  - スコア推移カード内で折れ線と run flow が縦に並ぶ layout にする
  - run flow は狭い幅で折り返し、version、点数、回答数、差分が重ならない状態にする
  - 折れ線は安定した高さを持ち、カード幅に追従して表示される
  - 既存 card/chip/select-row の見た目を壊さず、Course History の meta 追加には CSS 変更を要求しない
  - _Requirements: 2.5_

- [x] 2. Page test coverage
- [x] 2.1 Course Editor のスコア推移テストを更新・追加する
  - 既存 Before / After 期待を `スコアの推移`、`改善メトリクス`、raw 点数、`pp` 差分の期待へ更新する
  - 3 件以上の採点済み run で全 version、区間スコア率差分、総スコア率差分が表示されることを確認する
  - 未採点、未計測、満点が正でない run が推移から除外されることを確認する
  - metrics 取得失敗時に講座編集フォームは表示され、推移カードは表示されないことを確認する
  - 最新パッチ link を含む講座状態カードの既存導線が残っていることを確認する
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 2.1, 2.2, 2.3, 2.4, 4.1, 4.2_

- [x] 2.2 (P) Course History の version 平均点テストを追加する
  - metrics mock の default を空 run にし、既存履歴テストが平均点なしで通ることを確認する
  - 採点済み run のある version 行に平均点が表示されることを確認する
  - 採点済み run のない version 行には平均点が表示されないことを確認する
  - 満点が正でない run は Course History の平均点 meta に表示されないことを確認する
  - 同一 version の複数 run では metrics 応答順の最後が表示値になることを確認する
  - metrics 取得失敗でも version 一覧と diff が表示されることを確認する
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - _Boundary: CourseHistoryVersionScores, PageTests_
  - _Depends: 1.3_

- [x] 2.3 Owner/learner/API 境界の regression を確認する
  - 変更範囲が owner 向け Course Editor と Course History と metrics styling に閉じていることを確認する
  - API 型、API client、backend、learner page を変更せずに要件を満たしていることを確認する
  - 受講者向け画面に平均点推移、version 別平均点、差分 chip が追加されていないことを確認する
  - boundary 確認後、対象外ファイルに不要な変更が残っていない状態になる
  - _Requirements: 4.3, 4.4, 4.5_

- [x] 3. Validation
- [x] 3.1 Frontend の focused test、typecheck、lint を実行する
  - Course Editor と Course History の page tests が green になる
  - frontend typecheck が green になる
  - frontend lint が green になる
  - 可能な範囲で desktop/mobile 幅の表示を確認し、metrics flow に明らかな重なりがないことを確認する
  - 検証結果として、実行したコマンドと未実行の確認項目が分かる状態になる
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5_
