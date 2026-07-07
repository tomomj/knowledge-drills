# Requirements Document

## Introduction

Google Login Owner Scope は、審査員や利用者が Google ログイン後に自分専用の講座を作成・編集・分析できるようにしつつ、受講者向け share URL はログイン不要のまま維持するための最小認証・所有権機能である。

目的は本格的なユーザー管理やチーム権限を作ることではなく、公開デモ URL で複数利用者が管理操作を試しても、講座データが混線・破壊されない状態にすることである。

## Boundary Context

- **In scope**: Google ログイン、Firebase ID token 検証、現在ユーザー取得、最小 user profile 保存、`courses.ownerUserId` による所有権保存、講座・ドリル管理・分析・Patch 管理 API の owner check、受講者 share URL の認証除外、local / CI 用の認証なしモード。
- **Out of scope**: パスワード認証、メール招待、workspace、team、role、admin console、講座共有、課金、監査ログ、Firestore security rules による browser direct access、受講者ログイン。
- **Adjacent expectations**: Firebase / Google の認証情報はアプリ DB に保存しない。アプリ DB には所有権判定に必要な `uid` と最小 profile だけ保存する。審査員は Google ログイン後、自分の講座を自由に作成・編集・分析できる。

## Requirements

### Requirement 1: Google ログイン

**Objective:** As a 審査員・講座オーナー, I want Google アカウントでログインできる, so that 自分専用の講座管理画面を安全に操作できる

#### Acceptance Criteria
1. When 未ログイン利用者が管理画面を開く, the Knowledge Drills frontend shall Google ログイン導線を表示する
2. When 利用者が Google ログインを完了する, the Knowledge Drills frontend shall 管理画面を表示する
3. When 利用者がログアウトする, the Knowledge Drills frontend shall 管理 API に認証 token を送らない
4. The Knowledge Drills frontend shall Firebase / Google の API key を secret として扱わず、secret は backend にも保存しない

### Requirement 2: Backend ID token 検証

**Objective:** As a 運用者, I want backend が認証済みユーザーだけを信頼する, so that frontend から偽装された ownerUserId を受け付けない

#### Acceptance Criteria
1. When 管理 API が呼び出される, the Knowledge Drills backend shall `Authorization: Bearer <Firebase ID token>` を検証する
2. If token が欠落している, the Knowledge Drills backend shall `401 authentication_required` を返す
3. If token が不正または期限切れである, the Knowledge Drills backend shall `401 invalid_auth_token` を返す
4. The Knowledge Drills backend shall request body の `ownerUserId` を信頼せず、検証済み token の `uid` を所有者 ID として使う
5. If Firebase 認証設定が不足している, the Knowledge Drills backend shall `500 auth_not_configured` を返し、設定不足をログに記録する

### Requirement 3: 最小 user profile 保存

**Objective:** As a 利用者, I want 初回ログイン時にアカウントが作られる, so that 自分の講座を継続して管理できる

#### Acceptance Criteria
1. When ログイン済み利用者が `/api/me` を呼び出す, the Knowledge Drills backend shall `users/{uid}` を作成または更新する
2. The Knowledge Drills backend shall `users/{uid}` に `uid`、`email`、`displayName`、`photoUrl`、`createdAt`、`lastLoginAt` を保存できる
3. The Knowledge Drills backend shall user profile を認可判断の唯一の根拠にせず、認可判断には検証済み token の `uid` を使う

### Requirement 4: Course owner scope

**Objective:** As a 講座オーナー, I want 自分の講座だけを管理できる, so that 他の利用者の講座を誤って変更しない

#### Acceptance Criteria
1. When ログイン済み利用者が講座を作成する, the Knowledge Drills backend shall `courses.ownerUserId` に現在ユーザーの `uid` を保存する
2. When ログイン済み利用者が講座一覧を取得する, the Knowledge Drills backend shall `ownerUserId` が現在ユーザーの `uid` と一致する講座だけを返す
3. When ログイン済み利用者が講座詳細・更新・履歴・差分を要求する, the Knowledge Drills backend shall 対象講座の owner check を行う
4. If 対象講座が存在しない、または現在ユーザーの所有講座ではない, the Knowledge Drills backend shall `404 course_not_found` を返す
5. If 既存 Course document に `ownerUserId` が存在しない, the Knowledge Drills backend shall 500 にせず、現在ユーザーの所有講座ではないものとして扱う

### Requirement 5: Drill / Analysis / Patch owner check

**Objective:** As a 講座オーナー, I want ドリル生成・回答確認・分析・Patch 操作が自分の講座に限定される, so that 他の利用者の管理データや AI 実行を操作できない

#### Acceptance Criteria
1. When ドリル生成が要求される, the Knowledge Drills backend shall 対象講座が現在ユーザーの所有講座であることを確認してから Agent を呼び出す
2. When 管理者向け drill run / answers / analysis が要求される, the Knowledge Drills backend shall drill run の `courseId` から講座を取得して owner check を行う
3. When Patch 取得・Apply・Reject が要求される, the Knowledge Drills backend shall Patch の `courseId` から講座を取得して owner check を行う
4. If drill run または Patch が現在ユーザーの所有講座に紐づかない, the Knowledge Drills backend shall resource not found 相当の 404 を返す

### Requirement 6: 受講者 share URL の公開維持

**Objective:** As a 受講者, I want ログインなしで share URL から回答できる, so that 講座オーナーが受講者に簡単に配布できる

#### Acceptance Criteria
1. The Knowledge Drills backend shall `/api/drills/{shareToken}` と `/api/drills/{shareToken}/answers` を認証不要のまま維持する
2. The Knowledge Drills backend shall share token が無効な場合に `404 invalid_share_token` を返す
3. The Knowledge Drills backend shall 受講者 API response に `rubric` と `idealAnswer` を含めない
4. The Knowledge Drills frontend shall `/drills/{shareToken}` では Google ログインを要求しない

### Requirement 7: Local / CI 独立性

**Objective:** As a 開発者, I want 外部認証設定なしで local / CI のテストを実行できる, so that 自動テストが Firebase に依存しない

#### Acceptance Criteria
1. The Knowledge Drills backend shall `KNOWLEDGE_DRILLS_AUTH_MODE=none|firebase` で認証モードを切り替えられる
2. Where `auth_mode=none`, the Knowledge Drills backend shall local 固定 user id を現在ユーザーとして扱える
3. Where `auth_mode=firebase`, the Knowledge Drills backend shall Firebase project 設定が欠落している場合に起動時または初回検証時に明確なエラーを出す
4. The Knowledge Drills frontend tests shall Firebase 実接続なしで auth state を mock できる

### Requirement 8: Production deploy 設定

**Objective:** As a 運用者, I want 公開デモ環境で認証設定が確実に有効化される, so that ローカルでは動くがデプロイ環境では未認証または起動不能になる状態を避けられる

#### Acceptance Criteria
1. The Knowledge Drills Terraform shall backend Cloud Run に `KNOWLEDGE_DRILLS_AUTH_MODE=firebase` と `KNOWLEDGE_DRILLS_FIREBASE_PROJECT_ID` を設定できる
2. The Knowledge Drills CD workflow shall frontend build に `VITE_FIREBASE_API_KEY`、`VITE_FIREBASE_AUTH_DOMAIN`、`VITE_FIREBASE_PROJECT_ID`、`VITE_FIREBASE_APP_ID` を渡せる
3. If CD に必要な Firebase frontend 設定が欠落している, the Knowledge Drills CD workflow shall deploy を失敗させる
4. The Knowledge Drills deploy documentation shall Firebase Authentication の Google provider、authorized domain、GitHub repository variables、Cloud Run backend env の設定手順を含める
