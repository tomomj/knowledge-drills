# Requirements Document

## Introduction

Analysis UI Declutter は、ドリル確認(Drill Admin)とパッチレビュー(Patch Review)の
情報過多を解消する owner 向けフロントエンド整理である。

現状の両画面はすべての情報が同じ強さで並んでおり、ライフサイクル段階ごとの主目的
(生成直後 = 共有 URL の配布、回答収集中 = 採点状況の確認、分析中 = タイムライン、
レビュー時 = diff と判断ログ)が読み取りにくい。ハッカソン提出動画の撮影(後戻り不可)から
逆算し、情報を削除するのではなく、表示するタイミングと階層を整理して各段階の主役を立てる。

セッション内で合意した HTML モック(動画ショット別モック)が本 spec の入力資料である。
実装仕様の正は本 requirements とし、承認後は同じ spec ディレクトリの design/tasks を含める。

## Boundary Context

- **In scope**: ドリル確認画面の情報階層整理(講座管理と同じ main + サイドの 2 カラム化、共有 URL・状態・採点状況のサイド集約、設問詳細の折りたたみ、空状態案内の統合)、分析タイムラインの実行状態表示(実行中・完了・未開始・失敗の区別、進行中の段階表示)、分析実行中の画面フォーカス制御、パッチレビューの diff メタ情報・根拠表示の一元化・生 ID の非表示。すべてフロントエンドのみの変更。
- **Out of scope**: backend / API / agent の変更、スコア推移カード(`score-progression-ui` spec が担当)、パッチ見送り判断(no-patch 分岐)、初回ログイン時のデモ講座シード、講座一覧のダッシュボード化、受講者向け画面の変更。
- **Adjacent expectations**: `hackathon-feedback-loop` spec で導入済みの API 応答(analysisTimeline の status / summary / evidence / completedAt、scoreSummary、DocumentPatch の diffText / failureSignals / riskNotes / baseMarkdown)をそのまま使う。分析中の 1 秒ポーリングによる timeline 更新機構は現状のまま利用する。API には独立検証エージェントの結果を示すフィールドが存在しないため、検証結果を示すチェック表示(「検証済みチェック」カード)は本 spec の対象外とし、実在しない検証主体を示す表示は追加しない。

## Requirements

### Requirement 1: ドリル確認画面の情報階層を整理する

**Objective:** As a 講座オーナー, I want ドリル確認画面で配布・回答収集の各段階の主目的が最初に見える, so that 迷わず次の操作(配布・分析)に進める

#### Acceptance Criteria

1. Where 2 カラム表示が可能な画面幅である, the Knowledge Drills frontend shall 主内容(設問一覧・回答一覧・分析タイムライン)と補助情報(共有 URL・ドリルの状態・採点状況)を、講座管理画面と同じ main + サイドの 2 カラム構成で並置する
2. Where 画面幅が狭い表示環境である, the Knowledge Drills frontend shall 1 カラムに折り返し、共有 URL とドリルの状態を主内容より先に表示する
3. When オーナーがドリル確認画面を開く, the Knowledge Drills frontend shall 共有 URL を初期表示領域(スクロール前)で視認できる位置に表示する
4. The Knowledge Drills frontend shall ドリルの状態・資料バージョン・回答数・採点済み回答数を単一の状態表示に集約し、独立した stat 行(4 分割の統計表示)を表示しない
5. The Knowledge Drills frontend shall 同じ値(回答数等)を画面内の複数箇所に重複表示しない
6. The Knowledge Drills frontend shall 分析の実行可否を「回答を分析する」ボタンの活性状態で表現し、実行可否を示す独立のチップを表示しない
7. When 回答が 0 件である, the Knowledge Drills frontend shall 受講者への配布を促す案内を 1 箇所に集約し、採点状況と回答一覧に個別の空状態バナーを重複表示しない
8. If ドリル生成が失敗している, the Knowledge Drills frontend shall 既存のエラーバナー表示を維持する

### Requirement 2: 設問詳細を折りたたみで提供する

**Objective:** As a 講座オーナー, I want 設問一覧を設問文と出題意図中心で見渡せる, so that ページ全体の長さを抑えて採点状況や分析結果に素早く到達できる

#### Acceptance Criteria

1. When ドリル確認画面に設問一覧が表示される, the Knowledge Drills frontend shall 各設問の設問 ID・設問文・出題意図を常時表示する
2. The Knowledge Drills frontend shall 各設問の模範解答・教材の根拠・ルーブリックを設問ごとの折りたたみ領域に格納し、初期状態では閉じて表示する
3. When オーナーが設問の折りたたみを展開する, the Knowledge Drills frontend shall その設問の模範解答・教材の根拠・ルーブリックを表示する
4. When オーナーがキーボード操作で折りたたみを開閉する, the Knowledge Drills frontend shall マウス操作と同等に開閉できるようにする

### Requirement 3: 分析タイムラインを実行状態つきの実行ログとして表示する

**Objective:** As a 講座オーナー, I want 分析の進行・完了・失敗がステップごとに実行ログのように見える, so that Agent が何を根拠にどう判断したかを進行中でも追える

#### Acceptance Criteria

1. While 分析ステップが実行中である, the Knowledge Drills frontend shall 実行中を示す動きのあるインジケーターをそのステップに表示する
2. When 分析ステップが完了する, the Knowledge Drills frontend shall 完了を示すアイコンとともにそのステップの summary と根拠を表示する
3. While 分析ステップが未開始である, the Knowledge Drills frontend shall ステップ名を控えめな表現で表示し、summary と根拠を表示しない
4. If 分析ステップが失敗またはスキップとして報告される, the Knowledge Drills frontend shall 既存のステータス表現(失敗・スキップ)を維持して表示する
5. While 分析が実行中である, the Knowledge Drills frontend shall ポーリング更新で新たに完了したステップの内容を追加表示する
6. Where ステップの完了時刻が応答に含まれる, the Knowledge Drills frontend shall 完了時刻または前ステップからの経過時間をそのステップに表示する
7. Where 利用者の OS 設定で視覚効果の削減が有効である, the Knowledge Drills frontend shall 実行中インジケーターと出現アニメーションを無効化し、内容を即時表示する

### Requirement 4: 分析実行中はタイムラインを主要コンテンツにする

**Objective:** As a 講座オーナー, I want 分析中は画面がタイムラインに集中する, so that 分析の進行を見失わない

#### Acceptance Criteria

1. While 分析が実行中である, the Knowledge Drills frontend shall ドリル確認画面の設問一覧と回答一覧を折りたたみ、分析タイムラインを主要コンテンツとして表示する
2. When 分析が完了または失敗する, the Knowledge Drills frontend shall 設問一覧と回答一覧を再び閲覧可能な状態で提供する
3. The Knowledge Drills frontend shall 分析開始後の画面遷移挙動(完了時のパッチレビューへの遷移)を現状から変更しない

### Requirement 5: パッチレビューで変更規模と対象バージョンを一目で示す

**Objective:** As a 講座オーナー, I want パッチの変更規模と対象バージョンが diff 見出しでわかる, so that レビューの規模感と適用先を最初に把握できる

#### Acceptance Criteria

1. When diff が表示される, the Knowledge Drills frontend shall diff 見出しに追加行数と削除行数を表示する
2. When パッチが提案中であり適用元の講座バージョンが取得できる, the Knowledge Drills frontend shall 適用元バージョンと適用後バージョンを diff 見出しに表示する
3. If 講座バージョンの取得に失敗する, the Knowledge Drills frontend shall バージョン表記だけを省略し、diff 表示とレビュー操作を継続する
4. The Knowledge Drills frontend shall 検証結果を示すチェック一覧(検証済みチェック)を表示しない

### Requirement 6: パッチレビューの根拠を一元化する

**Objective:** As a 講座オーナー, I want 判断ログと根拠が一度ずつ読める, so that 同じ情報の二度読みなしに適用判断できる

#### Acceptance Criteria

1. When パッチレビュー画面に分析タイムラインが表示される, the Knowledge Drills frontend shall 各ステップの summary を常時表示し、根拠(evidence)は初期状態で閉じた折りたたみに格納する
2. When オーナーが根拠の折りたたみを展開する, the Knowledge Drills frontend shall 該当ステップの根拠を表示する
3. The Knowledge Drills frontend shall FailureSignal カードを誤答根拠の主要な提示場所として維持する
4. The Knowledge Drills frontend shall リスクノートを独立カードとして表示せず、修正案の根拠と同じカード群に統合して表示する
5. The Knowledge Drills frontend shall 生の drillRunId をパッチレビュー画面に表示しない
6. The Knowledge Drills frontend shall 回答サンプル数の表示を維持する

### Requirement 7: 既存の境界と体験を維持する

**Objective:** As a 講座オーナー, I want 今回の整理で既存の機能・境界が壊れない, so that 提出直前でも安心して変更を取り込める

#### Acceptance Criteria

1. The Knowledge Drills frontend shall 受講者向け画面の表示と挙動を変更しない
2. The Knowledge Drills frontend shall backend / API の変更を要求せず、既存応答 shape のまま表示を行う
3. The Knowledge Drills frontend shall 既存画面と一貫した視覚言語(カード・チップ・バナー)を維持する
4. The Knowledge Drills frontend shall 分析タイムライン取得のポーリング頻度を現状から変更しない
5. The Knowledge Drills frontend shall 既存の支援技術向けの名前(分析タイムライン・回答一覧等のアクセシブルな名前)を維持する
