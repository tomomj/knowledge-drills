# Requirements Document

## Introduction

Knowledge Drill MVP は、Markdown 講座を実務シナリオ型ドリルに変換し、受講者の回答結果から共通する誤答傾向を抽出し、講座オーナーが確認できる講座改善用 Document Patch を生成するアプリケーションである。MVP の目的は、受講者の誤答から生成された Document Patch が講座改善に使えるかを検証できる状態にすることである。

## Boundary Context

- **In scope**: 講座 Markdown の入力・保存、3 問固定の記述式ドリル生成、受講者向け共有 URL、回答提出、採点、誤答傾向分析、Document Patch 提案、差分確認、Apply / Reject、stale 判定。
- **Out of scope**: PDF アップロード、画像を含む講座解析、GitHub PR 作成、LMS 連携、本格的なログイン・権限管理、問題バンク、多肢選択式問題、講座プレビューの必須化。
- **Adjacent expectations**: MVP では本物の機密社内資料を扱わず、講座オーナーが Document Patch を人間として確認してから適用可否を判断する。受講者には採点根拠のうち rubric と ideal answer を公開しない。

## Requirements

### Requirement 1: 講座 Markdown 管理
**Objective:** As a 講座オーナー, I want 講座タイトルと Markdown 本文を作成・更新できる, so that ドリル生成の元になる講座内容を管理できる

#### Acceptance Criteria
1. When 講座オーナーがタイトルと Markdown 本文を保存する, the Knowledge Drill shall 講座を保存し、保存済みの内容を再表示できる
2. If タイトルが空で保存される, the Knowledge Drill shall タイトルが必要であることを講座オーナーに表示する
3. If Markdown 本文が空で保存される, the Knowledge Drill shall Markdown 本文が必要であることを講座オーナーに表示する
4. If Markdown 本文が 20,000 文字を超えて保存される, the Knowledge Drill shall MVP の文字数上限を超えていることを講座オーナーに表示する
5. While 講座オーナーが講座を表示している, the Knowledge Drill shall 最新のドリル実行と最新の Document Patch の状態を確認できるようにする

### Requirement 2: 実務シナリオ型ドリル生成
**Objective:** As a 講座オーナー, I want 講座 Markdown から記述式ドリルを生成できる, so that 受講者が講座内容を実務判断として理解しているか確認できる

#### Acceptance Criteria
1. When 講座オーナーが保存済み講座からドリル生成を開始する, the Knowledge Drill shall 3 問の記述式ドリルを生成する
2. The Knowledge Drill shall 各問題を単なる用語説明ではなく、受講者が判断理由を書く実務シナリオ型の問題として生成する
3. The Knowledge Drill shall 各問題に問題意図、採点 rubric、理想回答、講座内の根拠箇所を含める
4. The Knowledge Drill shall 各問題の満点を 4 点にする
5. If 講座 Markdown に根拠がない内容が必要になる, the Knowledge Drill shall その内容を問題として生成しない
6. If ドリル生成に失敗する, the Knowledge Drill shall 講座オーナーが再試行できる失敗状態を表示する

### Requirement 3: ドリル確認と共有
**Objective:** As a 講座オーナー, I want 生成されたドリルを確認して共有 URL を取得できる, so that 受講者へ回答フォームを配布できる

#### Acceptance Criteria
1. When ドリル生成が完了する, the Knowledge Drill shall 講座オーナーに生成された 3 問と rubric 概要を表示する
2. When ドリル生成が完了する, the Knowledge Drill shall 受講者向け共有 URL を表示する
3. The Knowledge Drill shall 共有 URL に推測困難な共有トークンを使用する
4. While 講座オーナーがドリルを確認している, the Knowledge Drill shall 回答数を確認できるようにする
5. While 回答が 1 件以上存在する, the Knowledge Drill shall 講座オーナーが回答分析を開始できるようにする

### Requirement 4: 受講者回答フォーム
**Objective:** As a 受講者, I want 共有 URL からドリルに回答できる, so that 講座理解を記述式で提出できる

#### Acceptance Criteria
1. When 受講者が有効な共有 URL を開く, the Knowledge Drill shall 受講者名入力欄と 3 問の回答欄を表示する
2. The Knowledge Drill shall 受講者向け画面に rubric と理想回答を表示しない
3. If 受講者名が空で回答が提出される, the Knowledge Drill shall 受講者名が必要であることを表示する
4. If いずれかの回答本文が空で提出される, the Knowledge Drill shall すべての問題への回答が必要であることを表示する
5. When 受講者が有効な回答を提出する, the Knowledge Drill shall 提出完了と最小限のフィードバックを受講者に表示する
6. If 共有トークンが無効である, the Knowledge Drill shall ドリルを表示せず、共有 URL が無効であることを表示する

### Requirement 5: 回答採点
**Objective:** As a 講座オーナー, I want 受講者回答が rubric に基づいて採点される, so that 理解できている点と不足点を把握できる

#### Acceptance Criteria
1. When 受講者回答が提出される, the Knowledge Drill shall 各回答を対応する問題の rubric に基づいて採点する
2. The Knowledge Drill shall 各問題の採点結果に得点、満点、良い点、不足点、受講者向けフィードバック、誤答タグを含める
3. The Knowledge Drill shall 回答に書かれていない内容を補完して正答扱いしない
4. If 回答が短すぎる, the Knowledge Drill shall 回答を受け付けたうえで不足点として採点に反映する
5. If 採点に失敗する, the Knowledge Drill shall 回答提出を失敗状態として扱い、再試行可能であることを表示する

### Requirement 6: 誤答傾向分析
**Objective:** As a 講座オーナー, I want 複数回答から共通する誤答傾向を抽出できる, so that 講座ドキュメントの改善対象を特定できる

#### Acceptance Criteria
1. When 講座オーナーが回答分析を開始する, the Knowledge Drill shall 回答結果から共通する誤答傾向を Failure Signal として生成する
2. The Knowledge Drill shall Failure Signal にタイトル、重要度、根拠、推定原因、疑われるドキュメント上の不足、対象セクション、推奨変更を含める
3. The Knowledge Drill shall 個別の誤答だけではなく、複数回答に見られる傾向を優先して示す
4. If 回答数が 3 件未満である, the Knowledge Drill shall Failure Signal に回答数と信頼度に関する注記を含め、断定ではなく少数回答に基づく傾向として表示する
5. The Knowledge Drill shall 受講者の理解不足と講座ドキュメントの説明不足を区別して表示する
6. If 事実として確認できない会社ルールが必要になる, the Knowledge Drill shall その会社ルールを新規に作らない

### Requirement 7: Document Patch 提案
**Objective:** As a 講座オーナー, I want 誤答傾向に基づく講座改善案を確認できる, so that 講座本文を改善するか判断できる

#### Acceptance Criteria
1. When Failure Signal が生成される, the Knowledge Drill shall 講座 Markdown 全体に対する Document Patch を提案する
2. The Knowledge Drill shall Document Patch に改善後 Markdown、変更概要、リスク注記、差分を含める
3. The Knowledge Drill shall 既存の Markdown 構造を可能な限り維持する
4. The Knowledge Drill shall Failure Signal に対応する箇所へ最小限の変更を提案する
5. If 不確かな内容が含まれる, the Knowledge Drill shall その内容をリスク注記として表示する
6. The Knowledge Drill shall 人間の承認なしに Document Patch を講座へ適用しない

### Requirement 8: Patch レビューと適用
**Objective:** As a 講座オーナー, I want Document Patch を Apply または Reject できる, so that 講座改善を人間の判断で管理できる

#### Acceptance Criteria
1. While 講座オーナーが Patch レビュー画面を表示している, the Knowledge Drill shall 回答概要、平均点、Failure Signal、変更概要、リスク注記、差分を確認できるようにする
2. When 講座オーナーが proposed 状態の Document Patch を Apply する, the Knowledge Drill shall 講座 Markdown を改善後 Markdown に更新し、Patch を applied 状態にする
3. When 講座オーナーが proposed 状態の Document Patch を Reject する, the Knowledge Drill shall Patch を rejected 状態にする
4. When 講座オーナーがレビューコメントを入力して Apply または Reject する, the Knowledge Drill shall レビューコメントを Patch と関連付けて保存する
5. If Document Patch 生成後に講座 Markdown が変更されている, the Knowledge Drill shall Patch を stale 状態にし、再分析が必要であることを講座オーナーに表示する
6. If proposed 状態ではない Document Patch に Apply または Reject が要求される, the Knowledge Drill shall その操作を拒否し、現在の Patch 状態を表示する

### Requirement 9: MVP セキュリティと公開範囲
**Objective:** As a 講座オーナー, I want MVP 検証に必要な範囲で安全に共有・確認できる, so that 不要な情報公開や自動更新を避けられる

#### Acceptance Criteria
1. The Knowledge Drill shall 受講者向け画面と受講者向け応答に rubric と理想回答を含めない
2. The Knowledge Drill shall 共有トークンを知らない利用者にドリル内容を表示しない
3. The Knowledge Drill shall 本物の機密社内資料を使わない前提であることを講座オーナーが認識できるようにする
4. The Knowledge Drill shall 講座オーナーの明示操作なしに講座 Markdown を更新しない
5. The Knowledge Drill shall MVP では本格的なログイン・権限管理を提供対象外として扱う

### Requirement 10: 進行状態とエラー表示
**Objective:** As a 講座オーナー, I want 生成・採点・分析の進行状態と失敗理由を確認できる, so that 検証作業を中断せずに再試行できる

#### Acceptance Criteria
1. While ドリル生成が進行中である, the Knowledge Drill shall 講座オーナーに生成中であることを表示する
2. While 回答分析が進行中である, the Knowledge Drill shall 講座オーナーに分析中であることを表示する
3. If ドリル生成、採点、分析、または Patch 生成が失敗する, the Knowledge Drill shall 失敗状態と再試行可能なメッセージを表示する
4. If 生成結果または分析結果が期待される形式を満たさない, the Knowledge Drill shall その処理を失敗として扱い、不完全な結果を講座オーナーに確定表示しない
5. The Knowledge Drill shall 講座オーナーが主要な処理対象を識別できるように、講座、ドリル実行、回答、Patch の関連を画面上で追跡できるようにする
