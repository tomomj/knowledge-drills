# Requirements Document

## Introduction

Demo Course Seed は、新規オーナー(ハッカソン審査員を含む)の初回体験を成立させる機能である。
現状、初めてログインしたオーナーの講座一覧は空であり、プロダクトの価値である改善ループ
(誤答分析 → パッチ提案 → 適用 → スコア改善)を体験する導線が存在しない。

本機能は、講座を 1 件も持たないオーナーの初回アクセス時に、事前定義されたデモ講座 2 つを
そのオーナー所有のデータとして自動投入する。①は本ハッカソンの概要を独自要約した教材で、
採点済み回答つきのため入力なしで実エージェントの分析を体験できる(審査員は教材内容を
熟知しているため、設問・採点・パッチ提案の妥当性を自分の知識で検証できる)。②は改善を
3 周済みの教材で、スコア推移・更新履歴・適用済みパッチという「結果」を初回閲覧時から見せる。
あわせて講座一覧を改善ループの状態が読めるダッシュボードに拡張する。

セッション内で合意した HTML モック(動画ショット別モック Shot 1)が入力資料である。

## Boundary Context

- **In scope**: 初回アクセス時のデモ講座投入機構(backend、冪等)、デモ 2 講座の固定データ(教材・ドリル・採点済み回答・更新履歴・適用済みパッチ)、講座削除(API + UI、オーナー本人のみ)、講座一覧のスパークライン・デモ表記・誘導バッジ・初回案内バナー、講座一覧応答へのスコア要約の後方互換な追加。
- **Out of scope**: 分析・採点・パッチ生成ロジックの変更、agent の変更、ドリル確認・パッチレビュー画面の変更(`analysis-ui-declutter` が担当)、講座管理のスコア推移カード(実装済み)、講座を既に持つ既存オーナーへの遡及シード、デモ講座の再投入機能。
- **Adjacent expectations**: デモ講座②のデータは、実装済みのスコア推移カード(`score-progression-ui`)と更新履歴の平均点表示が追加実装なしで表示される形で投入する。デモ講座①の分析は `real-agent-invocation` で導入済みの実 agent 機構をそのまま使う(シード側でモックしない)。講座一覧の行レイアウト変更は本 spec が所有し、`analysis-ui-declutter` とファイル重複しない。

## Requirements

### Requirement 1: 講座を持たないオーナーへの初回デモ投入

**Objective:** As a 新規オーナー(審査員), I want ログイン直後からデモ講座が用意されている, so that 何も入力せずにプロダクトの価値を体験し始められる

#### Acceptance Criteria

1. When 認証済みオーナーが講座一覧を取得し、そのオーナーの講座が 0 件かつ過去にデモ投入が行われていない, the Knowledge Drills backend shall デモ講座 2 つをそのオーナー所有のデータとして投入し、同じ一覧取得の応答に含める
2. The Knowledge Drills backend shall デモ投入をオーナーごとに最大 1 回に限定する
3. When オーナーがデモ講座を削除した後に講座一覧を再取得する, the Knowledge Drills backend shall デモ講座を再投入しない
4. When 講座を 1 件以上持つオーナーが講座一覧を取得する, the Knowledge Drills backend shall デモ投入を行わない
5. The Knowledge Drills backend shall デモ投入において LLM / agent 呼び出しを行わず、事前定義された固定データのみを書き込む
6. If デモ投入が失敗する, the Knowledge Drills backend shall 講座一覧の取得自体は成功させ、投入失敗が一覧閲覧を妨げないようにする

### Requirement 2: 体験用デモ講座(ハッカソン参加ガイド)

**Objective:** As a 審査員, I want 自分が熟知した題材のドリルで分析をすぐ実行できる, so that 設問・採点・パッチ提案の妥当性を自分の知識で検証しながら改善ループを体験できる

#### Acceptance Criteria

1. The Knowledge Drills backend shall デモ講座①として、本ハッカソンの概要(テーマ・審査基準・必須技術・提出物)を独自に要約した Markdown 教材を version 1 で投入する
2. The Knowledge Drills backend shall デモ講座①の教材を公式ページの文章の転載ではなく、独自の要約・言い換えとして収録する
3. The Knowledge Drills backend shall デモ講座①の教材に意図的な記載不足を 1 箇所含める
4. The Knowledge Drills backend shall デモ講座①に生成済みドリル 1 件を投入し、各設問に設問文・出題意図・模範解答・ルーブリック・教材本文に実在する根拠引用を含める
5. The Knowledge Drills backend shall デモ講座①に採点済み回答 4 件(スコアとフィードバック付き)を投入し、誤答の過半数が教材の記載不足箇所に関連するつまずきになるようにする
6. When オーナーがデモ講座①のドリル確認を開く, the Knowledge Drills frontend shall 「回答を分析する」ボタンを活性状態で表示する
7. When オーナーがデモ講座①の分析を実行する, the Knowledge Drills backend shall 既存の実 agent 機構で分析を実行する(デモ用のモック応答を使わない)

### Requirement 3: 結果閲覧用デモ講座(改善 3 周済みの講座)

**Objective:** As a 審査員, I want 改善ループを回し終えた講座の結果を初回閲覧時から見られる, so that スコア改善の証拠(推移・履歴・パッチ)を自分の操作なしで確認できる

#### Acceptance Criteria

1. The Knowledge Drills backend shall デモ講座②として version 3 の講座と、version 1 から 3 までの更新履歴(差分を確認できる revision)を投入する
2. The Knowledge Drills backend shall デモ講座②の教材をエンジニアリング以外の業務題材(経費精算の判断基準)とする
3. The Knowledge Drills backend shall デモ講座②にバージョン別の採点済み drill run 3 件(平均点が version を追って上昇する)を投入する
4. When オーナーが投入直後にデモ講座②の講座管理を開く, the Knowledge Drills frontend shall 既存のスコア推移カードを追加実装なしで表示する
5. The Knowledge Drills backend shall デモ講座②に適用済みパッチ 1 件(分析タイムライン・判断ログ・diff 付き)を投入し、パッチレビュー画面で適用済み状態として閲覧できるようにする

### Requirement 4: 講座一覧の改善ループ表示

**Objective:** As a オーナー, I want 講座一覧で各講座の改善状況が一目でわかる, so that 開いた瞬間に「資料が改善され続けるシステム」だと理解できる

#### Acceptance Criteria

1. When 講座に採点済み run が 2 件以上存在する, the Knowledge Drills frontend shall 講座一覧の行にバージョンごとの平均点推移のミニ折れ線と平均点の要約(最初 → 最後)を表示する
2. When 講座の採点済み run が 2 件未満である, the Knowledge Drills frontend shall ミニ折れ線を表示せず、行の既存表示を維持する
3. When 支援技術がミニ折れ線を参照する, the Knowledge Drills frontend shall 平均点の推移を意味する代替ラベルを提供する
4. The Knowledge Drills frontend shall デモ講座の行にデモであることを示す表記を表示する
5. When 講座に採点済み回答があり分析が未実行のドリルが存在する, the Knowledge Drills frontend shall 分析を試せることを示す誘導バッジをその行に表示する
6. When デモ講座が一覧に存在する, the Knowledge Drills frontend shall 最初の一歩(体験用デモ講座を開いて分析する)を案内するバナーを一覧上部に表示する
7. The Knowledge Drills backend shall 講座一覧応答にスパークライン表示へ必要なスコア要約を後方互換な形で追加する
8. If 講座のスコア要約が応答に含まれない, the Knowledge Drills frontend shall 一覧表示を壊さず、ミニ折れ線だけを省略する

### Requirement 5: 講座の削除

**Objective:** As a オーナー, I want 不要になった講座(デモ講座を含む)を削除できる, so that 自分の教材で運用を始めた後に一覧を整理できる

#### Acceptance Criteria

1. When オーナーが自分の講座を削除する, the Knowledge Drills backend shall その講座を講座一覧と講座配下の画面から取得できなくする
2. When 削除された講座の共有 URL を受講者が開く, the Knowledge Drills frontend shall 既存の無効な共有 URL と同じ扱いで表示する
3. When オーナーが削除操作を行う, the Knowledge Drills frontend shall 実行前に確認ステップを提示する
4. If 認証済みオーナーが他のオーナーの講座に削除を要求する, the Knowledge Drills backend shall 既存の認可規則と同様に 404 として扱う

### Requirement 6: 境界と既存動作の維持

**Objective:** As a オーナー, I want デモ投入が既存データや受講者体験に影響しない, so that 提出直前でも安心して導入できる

#### Acceptance Criteria

1. The Knowledge Drills backend shall 投入したデモデータを投入先オーナーのみが閲覧できるようにし、他のオーナーのデータに影響を与えない
2. The Knowledge Drills frontend shall デモ講座においても受講者向け画面の表示規則(rubric・idealAnswer・タイムライン等の非表示)を通常講座と同一に保つ
3. The Knowledge Drills backend shall 既存の講座・ドリル・パッチ API の応答 shape を後方互換に保つ(追加フィールドのみ許可)
4. The Knowledge Drills backend shall 投入するデモデータを、既存の schema 検証(根拠引用の教材実在チェック等)を満たす形で定義する
