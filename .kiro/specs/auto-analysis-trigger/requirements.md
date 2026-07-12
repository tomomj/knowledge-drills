# Requirements Document

## Introduction

Knowledge Drills の講座オーナーは現在、講座一覧やドリル管理画面に表示された要分析の警告を確認し、
手動で「回答を分析する」を実行しなければ、AI による教材改善案を得られない。そのため、回答の監視と
警告までは自動化されている一方、調査開始は人間の操作に依存している。

本仕様は、採点済みの未分析回答が対象ドリルに 5 件以上蓄積し、既存の要分析判定も成立した場合に、
既存の回答分析を自動起動する。分析結果として改善が必要な場合だけパッチ案を作成し、教材への適用または
却下は従来どおり講座オーナーが判断する。これにより、監視、警告、AI による調査・提案、人間による承認
という改善ループを成立させる。

## Boundary Context

- **In scope**: 採点成功時の自動起動判定、対象ドリルの未分析回答 5 件という起動閾値、既存の要分析判定との
  組み合わせ、自動・手動の重複起動抑止、自動分析では分析開始時点の採点済みかつスコア確定済みの回答だけを
  消化する挙動、改善不要時と失敗時の扱い、自動起動元の記録と管理画面での表示。
- **Out of scope**: 教材変更の自動適用・自動却下、既存の要分析判定ルールの変更、定期実行による再評価、
  分析失敗直後の即時リトライ、回答採点以外のイベントによる自動起動、既存データの一括移行、旧実行環境との
  混在移行、分散実行基盤や障害復旧基盤の強化、利用者向けの自動分析設定画面と講座ごとの設定、
  分析内容・プロンプト・パッチ品質判定の変更、プロセス停止・実行環境終了・再デプロイなどのインフラ中断で
  終了状態を記録できなかった分析の回収、および残留した分析中状態の自動復旧。
- **Adjacent expectations**: 要分析状態と未分析回答の定義、分析済み回答件数の記録、および分析からパッチ案作成
  までの判断は既存機能の契約を維持する。本仕様は既存の手動分析、パッチの適用・却下、講座オーナーの認可を
  変更せず、自動起動の契機と起動元の可視化だけを追加する。Requirement 2.6–2.8 の分析失敗は、実行中の
  プロセスが例外を捕捉して失敗状態を記録できた場合を対象とし、インフラ中断で記録できない場合は含めない。

## Requirements

### Requirement 1: 採点成功時の自動分析判定

**Objective:** As a 講座オーナー, I want 低スコア回答が十分に蓄積したドリルの分析が自動で始まる, so that 警告を確認して調査ボタンを押さなくても改善案を受け取れる

#### Acceptance Criteria

1. When 受講者回答の採点が成功する, the Knowledge Drills backend shall 回答が投稿された対象ドリルについて自動分析の起動条件を評価する
2. When 自動分析の起動条件を評価する, the Knowledge Drills backend shall 対象ドリルが講座の現行の資料 version に属し、そのドリルの採点済み未分析回答が 5 件以上あり、講座の既存の要分析判定が成立し、対象ドリルが分析中ではなく、同じ講座にレビュー待ちのパッチ案がない場合に限り自動分析を開始する
3. When 対象ドリルの未分析回答を数える, the Knowledge Drills backend shall 現行の資料 version に属する対象ドリルの採点済み回答だけを集計し、既存の分析済み回答件数に含まれる回答を除外する
4. If 採点中、採点失敗、またはスコア未確定の回答が存在する, the Knowledge Drills backend shall その回答を自動起動閾値の件数に含めない
5. If 自動分析の起動条件のいずれかが成立しない, the Knowledge Drills backend shall 自動分析を開始せず、回答の採点結果と既存の手動分析機能を変更しない
6. The Knowledge Drills backend shall 自動分析の起動閾値を未分析回答 5 件とする

### Requirement 2: 採点体験と分析対象の分離

**Objective:** As a 受講者, I want 回答送信が自動分析の所要時間や成否に影響されない, so that 従来どおり採点結果を受け取れる

#### Acceptance Criteria

1. When 回答の採点が成功し自動分析の起動条件が成立する, the Knowledge Drills backend shall 受講者へ採点結果を返す処理を自動分析の完了待ちによって阻害しない
2. When 自動分析を開始する, the Knowledge Drills backend shall 分析開始時点で対象ドリルに存在する採点済み回答のうち、合計スコアと最大スコアが存在し最大スコアが正である回答だけを今回の分析対象として確定する
3. When 自動分析が成功する, the Knowledge Drills backend shall 分析開始時点で今回の分析対象として確定した回答だけを分析済みとして扱う
4. If 自動分析の実行中に新しい回答の採点が成功する, the Knowledge Drills backend shall その回答を今回の分析済み回答に含めず、次回以降の自動分析判定に使用する未分析回答として維持する
5. If 自動分析の最終分析結果に Failure Signal が存在しない, the Knowledge Drills backend shall パッチ案を作成せずに分析を正常完了し、今回の分析対象として確定した回答を分析済みとして扱う
6. If 自動分析が失敗する, the Knowledge Drills system shall 今回の分析対象を未分析のまま維持し、ドリル管理画面の分析タイムラインに失敗を表示して、講座オーナーが手動分析を再実行できる状態にする
7. If 自動分析が失敗する, the Knowledge Drills backend shall 失敗直後の即時再実行および定期的な自動再実行を行わず、次の回答の採点成功時に通常の起動条件を再評価する
8. If 自動分析が失敗する, the Knowledge Drills backend shall 受講者へ返却済みの採点結果を変更しない

### Requirement 3: 評価タイミングと重複起動の抑止

**Objective:** As a 講座オーナー, I want 自動分析が予測可能なタイミングで一度だけ起動する, so that 重複した分析やパッチ案に対応せずに済む

#### Acceptance Criteria

1. When 回答の採点成功以外の操作または定期更新が行われる, the Knowledge Drills backend shall その操作または更新を理由に自動分析を開始しない
2. If 自動分析機能の提供開始時点ですでに未分析回答が 5 件以上存在する, the Knowledge Drills backend shall 機能提供開始だけを理由に自動分析を開始せず、次の回答の採点成功時に起動条件を評価する
3. If レビュー待ちのパッチ案が適用または却下される, the Knowledge Drills backend shall パッチ案の解消だけを理由に自動分析を開始せず、次の回答の採点成功時に起動条件を評価する
4. While 対象ドリルの分析が実行中である, the Knowledge Drills backend shall 同じ対象ドリルの自動分析を追加で開始しない
5. When 同じ対象ドリルに対する複数の自動分析の開始が競合する, the Knowledge Drills backend shall その対象ドリルで開始される自動分析を高々 1 件にする
6. When 同じ対象ドリルに対する手動分析と自動分析の開始が競合する, the Knowledge Drills backend shall その対象ドリルで開始される分析を高々 1 件にする
7. While 同じ講座にレビュー待ちのパッチ案が存在する, the Knowledge Drills backend shall その講座に属するドリルの自動分析を開始しない
8. If 分析中またはレビュー待ちのパッチ案があるため自動分析を開始しない, the Knowledge Drills backend shall 既存の分析状態およびパッチ案を変更しない

### Requirement 4: 人間による教材変更の承認

**Objective:** As a 講座オーナー, I want AI が作成した改善案を確認してから教材へ反映する, so that 自動化しても教材変更の最終判断を維持できる

#### Acceptance Criteria

1. When 自動分析が改善の必要性を認める, the Knowledge Drills backend shall 既存のレビュー待ちパッチ案として改善案を作成する
2. When 自動分析がパッチ案を作成する, the Knowledge Drills system shall そのパッチ案を自動で教材へ適用または却下しない
3. The Knowledge Drills system shall 自動分析で作成されたパッチ案に対して既存の講座オーナーによる適用・却下操作を提供する
4. The Knowledge Drills system shall 既存の手動分析機能を引き続き提供する
5. If 自動分析の起動条件が成立しない, the Knowledge Drills system shall 講座オーナーによる手動分析の可否を自動起動条件によって制限しない

### Requirement 5: 自動起動の記録と表示

**Objective:** As a 講座オーナーおよびデモ閲覧者, I want AI が人間の操作なしに開始した分析を識別できる, so that 自律的な改善提案であることと実行履歴を確認できる

#### Acceptance Criteria

1. When 自動分析が開始される, the Knowledge Drills backend shall その分析の起動元を自動として記録する
2. When 手動分析が開始される, the Knowledge Drills backend shall その分析の起動元を自動分析と区別可能な状態で維持する
3. When 講座オーナーが自動分析の分析タイムラインを閲覧する, the Knowledge Drills frontend shall 「AI 自動分析」であることを手動分析と区別して表示する
4. When 講座オーナーが自動分析によって作成されたパッチ案を閲覧する, the Knowledge Drills frontend shall 「AI 自動分析」による提案であることを表示する
5. While 表示対象が手動分析である, the Knowledge Drills frontend shall 既存の手動分析表示を変更しない
