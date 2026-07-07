# Implementation Plan

- [ ] 1. Foundation: 認証・所有権の前提設定を追加する
- [x] 1.1 backend の認証モード設定と Firebase Admin 依存を追加する
  - `auth_mode=none|firebase`、Firebase project id、local 固定ユーザー設定を既存の設定 prefix で読み込めるようにする。
  - Firebase Admin SDK を backend runtime 依存に追加し、lockfile と依存検証を更新する。
  - 完了条件: 設定の既定値は外部 Firebase なしで既存 local / CI テストを起動でき、`firebase` mode では project id 不足を検出できる。
  - _Requirements: 2.5, 7.1, 7.2, 7.3_

- [ ] 1.2 frontend の Firebase SDK と公開 build 設定を追加する
  - Firebase client SDK を frontend 依存に追加し、Vite env で Firebase web config を参照できるようにする。
  - frontend Docker build に Firebase 用 build arg を追加し、API key を secret として扱わない構成にする。
  - 完了条件: frontend build が Firebase env を受け取れる状態になり、backend secret や Admin credentials は frontend に含まれない。
  - _Requirements: 1.4, 8.2_

- [ ] 1.3 認証テスト用の差し替え境界を整える
  - backend route / service tests で fake auth client を注入できる前提を作る。
  - frontend tests で Firebase 実接続なしに auth state と ID token を mock できる前提を作る。
  - 完了条件: 認証関連テストが外部 Firebase project や Google ログイン画面に依存せずに記述できる。
  - _Requirements: 7.4_

- [ ] 2. Backend auth: ID token 検証と現在ユーザー API を実装する
- [ ] 2.1 認証 client 境界と FastAPI dependency を実装する
  - Firebase token 検証、local 固定ユーザー、設定不備 client を同じ認証境界で扱う。
  - `Authorization: Bearer` 欠落・形式不正・期限切れ・不正 token・Firebase 初期化不備を API error code に変換する。
  - ログには設定不備や例外種別だけを残し、ID token 本体や講座・回答本文を出さない。
  - 完了条件: 管理 API から呼べる current user dependency が、成功時は検証済み `uid` を返し、失敗時は設計どおりの 401 / 500 を返す。
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 7.1, 7.2, 7.3_

- [ ] 2.2 user profile の保存と `/api/me` を実装する
  - `users/{uid}` に最小 profile を作成または更新し、`createdAt` と `lastLoginAt` を扱う。
  - `/api/me` は current user を必須にし、profile の存在ではなく検証済み token の `uid` を認可判断の根拠にする。
  - 完了条件: ログイン済み user で `/api/me` を呼ぶと profile が upsert され、response で現在ユーザーを確認できる。
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] 2.3 管理 route に認証を配線し、learner route を公開のまま維持する
  - Course、admin drill run、analysis、Patch の管理 route に current user dependency を追加する。
  - `/api/drills/{shareToken}`、`/api/drills/{shareToken}/answers`、`/api/learn/{shareToken}`、`/api/learn/{shareToken}/answers`、`/health` は認証不要のまま残す。
  - 完了条件: `auth_mode=firebase` では token なしの管理 API は 401 になり、`auth_mode=none` では token なしでも local user として管理 API を呼び出せる。
  - 完了条件: token なしの learner share URL API と legacy learner API は既存どおり呼び出せる。
  - _Requirements: 2.1, 2.2, 6.1, 6.2_

- [ ] 3. Backend owner scope: Course / Drill / Analysis / Patch を所有者単位に制限する
- [ ] 3.1 Course schema と repository を owner 対応にする
  - Course に nullable な `ownerUserId` を保存できるようにし、既存 ownerless document が validation error で 500 にならないようにする。
  - 新規 Course 作成では request body の `ownerUserId` を信頼せず、現在ユーザーの `uid` を保存する。
  - owner-scoped list query を追加し、管理 API の一覧では自分の Course だけを返す。
  - 完了条件: 新規 Course document には現在ユーザーの owner id が保存され、ownerless Course は一覧に出ない。
  - _Requirements: 2.4, 4.1, 4.2, 4.5_

- [ ] 3.2 Course service の詳細・更新・履歴・差分に owner check を適用する
  - Course detail、update、revision list、revision diff の前に `Course.ownerUserId` を照合する。
  - 存在しない Course、他 owner の Course、ownerless Course は同じ `404 course_not_found` として扱う。
  - Course detail と Course summary の response に不要な `ownerUserId` を露出しないよう、公開 response fields を明示する。
  - 完了条件: 他 owner または ownerless の Course URL を直接指定しても詳細・更新・履歴・差分は取得できない。
  - _Requirements: 2.4, 3.3, 4.3, 4.4, 4.5_

- [ ] 3.3 Drill / Analysis / Patch service に Course 経由の owner check を適用する
  - ドリル生成は対象 Course の owner check 後にだけ Agent を呼び出す。
  - admin drill run、answers、analysis は drill run の `courseId` から Course を辿って owner check する。
  - Patch 取得・Apply・Reject は patch の `courseId` から Course を辿って owner check する。
  - 完了条件: 他 owner の drill run は 404 `drill_run_not_found`、他 owner の patch は 404 `patch_not_found` になり、Agent 実行や Patch 更新は発生しない。
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 4. Frontend auth: Google ログイン、token 付与、route guard を実装する
- [ ] 4.1 frontend API client に auth token provider を追加する
  - React に依存しない token provider を追加し、API client が token 取得後に `Authorization: Bearer` を付ける。
  - ログアウト後や token 取得不能時は管理 API に Authorization header を送らない。
  - 完了条件: API client test で token ありは Bearer header 付き、token なしは header なしになる。
  - _Requirements: 1.3, 2.1_

- [ ] 4.2 Google ログイン画面と AuthProvider を実装する
  - Firebase auth state を `checking`、`signedOut`、`signedIn`、`failed` の明示状態として扱う。
  - 未ログインの管理画面では Google ログイン導線だけを表示し、ログイン成功後に `/api/me` を呼ぶ。
  - `/api/me` 失敗時は管理画面を表示せず、再試行または再ログイン可能な状態を表示する。
  - 完了条件: mock auth state で未ログイン、ログイン成功、backend 確認失敗の画面遷移を確認できる。
  - _Requirements: 1.1, 1.2, 1.3, 3.1_

- [ ] 4.3 管理 route guard と learner route の公開例外を実装する
  - `/courses` 配下と `/patches/:patchId` を認証必須 route にする。
  - `/drills/:shareToken` は AuthProvider の signed-in requirement から外し、未ログインでも回答画面を表示する。
  - 401 を受けた管理画面は再ログイン可能な状態へ戻す。
  - 完了条件: 未ログインでは管理 route がログイン画面になり、learner share URL はログイン画面に置き換わらない。
  - _Requirements: 1.1, 1.2, 6.4_

- [ ] 5. Deploy configuration: production 認証設定を配線する
- [ ] 5.1 (P) Terraform で backend Cloud Run の Firebase auth env を設定する
  - backend Cloud Run に `KNOWLEDGE_DRILLS_AUTH_MODE=firebase` と Firebase project id を渡す。
  - local の `auth_mode=none` 既定とは別に、production deploy では Firebase mode が有効になることを明示する。
  - 完了条件: Terraform plan 上で backend service の認証 env が確認できる。
  - _Requirements: 8.1_
  - _Boundary: Terraform_

- [ ] 5.2 (P) CD workflow と frontend Docker build に Firebase frontend config を渡す
  - GitHub repository variables から `VITE_FIREBASE_*` を読み、欠落時は CD validation で失敗させる。
  - frontend image build に API base URL と Firebase build args を渡す。
  - 完了条件: CD workflow は Firebase frontend config 不足を deploy 前に検出し、設定済みの場合は frontend image build に値を渡せる。
  - _Requirements: 1.4, 8.2, 8.3_
  - _Boundary: CD workflow, Frontend Dockerfile_

- [ ] 5.3 deploy documentation と既存 data の owner 移行メモを更新する
  - Firebase Authentication の Google provider、有効 domain、GitHub repository variables、backend env の設定手順を追加する。
  - 既存 demo Course を維持する場合の owner migration または seed 再作成手順を明記する。
  - 完了条件: deploy 前に必要な Firebase / Cloud Run / GitHub 変数と ownerless Course の扱いをドキュメントから確認できる。
  - _Requirements: 4.5, 8.4_

- [ ] 6. Validation: 回帰テストと境界テストを追加・実行する
- [ ] 6.1 backend 認証境界の unit / route tests を追加する
  - `auth_mode=none` の token 欠落時に local user として成功すること、Firebase mode project id 不足、`auth_mode=firebase` の token 欠落、形式不正、不正 token、fake auth client 成功を検証する。
  - `/api/me` の user profile upsert と、profile の存在を認可判断に使わないことを検証する。
  - 完了条件: 外部 Firebase 接続なしで認証境界の成功・失敗パターンがすべて自動テストで確認できる。
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 3.1, 3.2, 3.3, 7.1, 7.2, 7.3_

- [ ] 6.2 backend owner scope と learner 公開 API の integration tests を追加する
  - Course 作成・一覧・詳細・更新・履歴・差分が owner 単位で制限されることを検証する。
  - ownerless Course と他 owner の Course は 404 `course_not_found`、他 owner の drill run は 404 `drill_run_not_found`、他 owner の patch は 404 `patch_not_found` になることを検証する。
  - learner share URL API と legacy learner API は token なしで成功し、無効 token は `invalid_share_token`、response は `rubric` / `idealAnswer` なしであることを検証する。
  - 完了条件: 管理データの cross-owner access がすべて遮断され、learner 体験の既存回帰がない。
  - _Requirements: 2.4, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3_

- [ ] 6.3 frontend auth と routing の tests を追加する
  - auth state mock で未ログイン、ログイン成功、ログアウト、`/api/me` 失敗、401 後の再ログイン導線を検証する。
  - API client の Authorization header と `/drills/:shareToken` の公開表示を検証する。
  - 完了条件: Firebase 実接続なしで Google ログイン導線、管理 route guard、learner route 例外が自動テストで確認できる。
  - _Requirements: 1.1, 1.2, 1.3, 6.4, 7.4_

- [ ] 6.4 全体の lint / typecheck / test / plan validation を実行する
  - backend pytest、ruff、mypy を実行し、認証設定なしの CI 相当で通ることを確認する。
  - frontend lint、typecheck、unit test、必要な E2E を `auth_mode=none` 前提で実行する。
  - Terraform fmt / validate / plan と CD workflow の構文確認を行う。
  - 完了条件: 実装後の主要検証コマンドが成功し、Firebase 実接続なしの自動テスト独立性が維持される。
  - _Requirements: 7.1, 7.4, 8.1, 8.2, 8.3_
