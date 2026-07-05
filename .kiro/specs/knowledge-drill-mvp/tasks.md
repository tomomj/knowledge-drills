# Implementation Plan

- [x] 1. Foundation: プロジェクト骨格と実行基盤を作る
- [x] 1.1 Backend の実行・テスト基盤を用意する
  - FastAPI application を起動できる backend package と設定読み込みを作る。
  - Python 3.11+、Pydantic v2、Firestore SDK、Agent Platform SDK、pytest を依存関係に含める。
  - health check が成功し、backend test command が空の状態でも実行できる。
  - _Requirements: 10.3, 10.4_
  - _Boundary: Backend runtime_

- [x] 1.2 Frontend の実行・テスト基盤を用意する
  - Vite、React、TypeScript、React Router の application shell を作る。
  - owner 向け route と learner 向け route を配置できる routing skeleton を用意する。
  - frontend build と typecheck が成功する。
  - _Requirements: 4.1, 8.1, 10.5_
  - _Boundary: Frontend runtime_

- [x] 1.3 Agent app の実行骨格を用意する
  - ADK agent app の package、root agent、prompt 配置、local import を成立させる。
  - Agent Runtime deployment に必要な SDK dependency と設定項目を用意する。
  - local import check で agent package が読み込める。
  - _Requirements: 2.1, 5.1, 6.1, 7.1_
  - _Boundary: KnowledgeDrillAgentApp_

- [x] 1.4 共通のエラー、ログ、テスト方針を backend に通す
  - API error response の基本形を統一し、request id と主要 resource id をログに出せるようにする。
  - learner answer 全文を通常ログに出さない設定を用意する。
  - MVP では本格的なログイン・権限管理 middleware を導入しない境界を API bootstrap で明確にする。
  - validation error と system error が区別できるテストを追加する。
  - _Requirements: 9.1, 9.5, 10.3, 10.4, 10.5_
  - _Boundary: API Layer, Monitoring_

- [x] 2. Domain contracts and persistence: 型、永続化、低レベル utility を作る
- [x] 2.1 Domain / API / Agent schema を定義する
  - Course、DrillRun、AnswerSubmission、DocumentPatch、FailureSignal、Agent 入出力の schema を定義する。
  - learner response schema と admin response schema を分離し、learner schema に rubric と idealAnswer が含まれないことをテストする。
  - `sampleSize`、`confidenceNote`、answer status、patch status、drill_run status の union が型で表現される。
  - _Requirements: 2.3, 4.2, 5.2, 6.2, 6.4, 7.2, 9.1_
  - _Boundary: Domain schemas, API schemas, Agent schemas_

- [x] 2.2 Firestore repository と transaction 境界を用意する
  - Course、DrillRun、ShareToken、Answer、Patch の repository を作る。
  - Patch apply/reject と shareToken reservation で transaction / create-only 書き込みを使える。
  - repository test で create、lookup、status update、transaction callback が観測できる。
  - _Requirements: 1.1, 3.3, 8.2, 8.3, 8.5, 9.2_
  - _Boundary: Firestore Repositories_

- [x] 2.3 shareToken 生成と予約の一意性を実装する
  - 高エントロピー token を生成し、`share_tokens` 予約 document と drill_run 作成を同一 transaction にする。
  - forced collision 時に最大 3 回再生成し、それでも失敗した場合は drill generation を failed にできる。
  - collision を強制したテストで別 token が予約される。
  - _Requirements: 3.2, 3.3, 4.6, 9.2_
  - _Boundary: ShareTokenRepository, ShareToken utility_

- [x] 2.4 unified diff と Markdown patch 補助を実装する
  - baseMarkdown と patchedMarkdown から unified diff text を生成する。
  - 空 diff、複数行変更、Markdown 見出しを含む変更で diff が確認できる。
  - diffText が DocumentPatch に保存できる形で返る。
  - _Requirements: 7.2, 8.1_
  - _Boundary: Diff utility_

- [x] 2.5 Agent Runtime client の typed invocation と retry を実装する
  - Drill、grading、failure analysis、document patch の task 呼び出し口を用意する。
  - Agent 出力 schema 違反時は同一入力で 1 回だけ retry し、失敗理由を呼び出し元へ返す。
  - test double で成功、retry 成功、retry 後失敗を検証できる。
  - _Requirements: 2.1, 5.1, 6.1, 7.1, 10.4_
  - _Boundary: AgentRuntimeClient_

- [x] 3. Agent app: 生成・採点・分析・Patch 提案 agent を作る
- [x] 3.1 DrillGeneratorAgent の prompt と出力 contract を実装する
  - 3 問固定、実務シナリオ型、判断理由、rubric、idealAnswer、sourceEvidence を必須にする。
  - rubric points 合計 4 と course markdown に根拠がある内容だけを問う制約を prompt と schema に反映する。
  - local sample input で 3 問の schema-valid output を得られる。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - _Boundary: KnowledgeDrillAgentApp_
  - _Depends: 1.3, 2.1_

- [x] 3.2 GradingAgent の prompt と出力 contract を実装する
  - rubric に基づく得点、良い点、不足点、feedback、failureTags を返す。
  - 回答にない内容を補完しない制約と短すぎる回答を不足点として扱う制約を prompt に入れる。
  - local sample input で schema-valid grading result を得られる。
  - _Requirements: 5.1, 5.2, 5.3, 5.4_
  - _Boundary: KnowledgeDrillAgentApp_
  - _Depends: 1.3, 2.1_

- [x] 3.3 FailureAnalysisAgent と DocumentPatchAgent の prompt を実装する
  - Failure Signal に required fields、`sampleSize`、少数回答時の `confidenceNote` を含める。
  - 受講者を責めない、会社ルールを創作しない、最小限の Markdown 変更、riskNotes 出力を制約に入れる。
  - local sample input で Failure Signal と patchedMarkdown の schema-valid output を得られる。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.3, 7.4, 7.5_
  - _Boundary: KnowledgeDrillAgentApp_
  - _Depends: 1.3, 2.1_

- [x] 3.4 Agent app と backend schema の contract compatibility を検証する
  - Agent app output を backend の Agent schema で validation する contract test を追加する。
  - schema mismatch がある場合は test が失敗する。
  - Agent が Firestore path、Secret、admin token を要求しないことを確認する。
  - _Requirements: 2.3, 5.2, 6.2, 7.2, 9.1, 10.4_
  - _Boundary: KnowledgeDrillAgentApp, AgentRuntimeClient_

- [x] 4. Course and drill backend: Course 管理と Drill 生成を実装する
- [x] 4.1 Course CRUD と latest state を実装する
  - title / markdown 必須、20,000 文字上限、version increment を実装する。
  - course detail response に latestDrillRunId と latestPatchId を含める。
  - Course create / get / update API が保存済み内容を返す。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - _Boundary: CourseService, CourseRepository_
  - _Depends: 1.1, 2.1, 2.2_

- [x] 4.2 Drill generation lifecycle を実装する
  - saved course から `generating` drill_run を作成し、Agent 成功時に `ready` へ更新する。
  - Agent 出力の 3 問、rubric points、sourceEvidence を検証する。
  - 生成失敗時は drill_run を `failed` にし、errorMessage を保存して retry 可能な状態を返す。
  - _Requirements: 2.1, 2.3, 2.4, 2.6, 10.1, 10.3, 10.4_
  - _Boundary: DrillService, DrillRepository, AgentRuntimeClient_
  - _Depends: 2.3, 2.5, 3.1, 4.1_

- [x] 4.3 Drill admin API と answer count を実装する
  - generated questions、rubric summary、shareUrl、answerCount を owner 向けに返す。
  - answerCount は drillRunId に紐づく answers から算出される。
  - 1 件以上の回答がある場合に analysis を開始できる状態を返す。
  - _Requirements: 3.1, 3.2, 3.4, 3.5, 10.5_
  - _Boundary: DrillService, DrillRepository, AnswerRepository_

- [x] 4.4 Learner drill API と invalid token 応答を実装する
  - valid shareToken で learner 向けの 3 問を返す。
  - learner response から rubric と idealAnswer を除外する。
  - invalid shareToken は 404 `invalid_share_token` を返し、drill content を返さない。
  - _Requirements: 4.1, 4.2, 4.6, 9.1, 9.2_
  - _Boundary: DrillService, ShareTokenRepository_

- [x] 4.5 Course / Drill backend の unit と integration test を追加する
  - Course validation、drill generation success/failure、shareToken reservation collision、learner response leakage 防止をテストする。
  - forced token collision で別 token が作成されることを確認する。
  - test suite で Course と Drill の主要 API が通る。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.6, 3.3, 4.2, 4.6, 9.1, 9.2, 10.4_
  - _Boundary: CourseService, DrillService, Firestore Repositories_

- [x] 5. Answer and grading backend: 回答提出と採点を実装する
- [x] 5.1 SubmitAnswerRequest の整合性検証を実装する
  - learnerName 必須、answerText 必須、3 件ちょうどの answers を検証する。
  - questionId set が drill questions と完全一致しない場合、欠落、未知、重複を 400 として reject する。
  - invalid request では answer document が作成されない。
  - _Requirements: 4.3, 4.4, 5.1, 5.2_
  - _Boundary: AnswerService_

- [x] 5.2 Answer grading lifecycle を実装する
  - valid submission を `grading` として保存し、各回答を GradingAgent に送る。
  - 採点成功時は `graded`、totalScore、maxScore、gradingResults を保存する。
  - 採点失敗時は `failed` と errorMessage を保存し、retry 可能なエラーを返す。
  - _Requirements: 4.5, 5.1, 5.2, 5.5, 10.3, 10.4_
  - _Boundary: AnswerService, AnswerRepository, AgentRuntimeClient_
  - _Depends: 2.5, 3.2, 5.1_

- [x] 5.3 Learner feedback と非公開情報の遮断を実装する
  - submit response は提出完了と最小限の feedback だけを返す。
  - rubric、idealAnswer、管理用採点根拠が learner response に含まれないことを保証する。
  - 短すぎる回答は採点に流れ、不足点として feedback に反映される。
  - _Requirements: 4.2, 4.5, 5.4, 9.1_
  - _Boundary: AnswerService, API schemas_

- [x] 5.4 Answer backend の unit と integration test を追加する
  - invalid token、空 learnerName、空 answerText、欠落 questionId、未知 questionId、重複 questionId を検証する。
  - grading success と grading failure の status 永続化を検証する。
  - learner response に rubric と idealAnswer がないことを test で確認する。
  - _Requirements: 4.2, 4.3, 4.4, 4.6, 5.1, 5.2, 5.5, 9.1, 9.2_
  - _Boundary: AnswerService, AnswerRepository_

- [x] 6. Analysis and patch backend: 分析、Patch 提案、Apply / Reject を実装する
- [x] 6.1 Analysis state transition と retry 条件を実装する
  - analyze 開始時に analyzable status を判定し、`analyzing` に更新する。
  - 1 件以上の graded answer がない場合は 400 `no_graded_answers` を返す。
  - analysis failure 由来の failed は再分析可能、drill generation failure 由来の failed は 409 `drill_not_analyzable` を返す。
  - _Requirements: 3.5, 6.1, 10.2, 10.3, 10.5_
  - _Boundary: AnalysisService, DrillRepository_

- [x] 6.2 Failure analysis と Document Patch 生成を実装する
  - graded answers だけを分析入力にし、failed / grading answers を除外して log / response に含める。
  - Failure Signal に required fields、`sampleSize`、少数回答時の `confidenceNote` を保存する。
  - DocumentPatchAgent output から patchedMarkdown、patchSummary、riskNotes を受け取り、diffText を生成する。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5_
  - _Boundary: AnalysisService, AgentRuntimeClient, Diff utility_
  - _Depends: 2.4, 2.5, 3.3, 6.1_

- [x] 6.3 Analysis 成功・失敗時の永続状態更新を実装する
  - 成功時は patch を `proposed` で保存し、drill_run を `analyzed` にし、course.latestPatchId と latestDrillRunId を更新する。
  - Agent、schema validation、diff、保存の失敗時は drill_run を `failed` にして errorMessage を保存する。
  - Course detail から最新 patch が追跡できる。
  - _Requirements: 1.5, 7.1, 7.2, 10.2, 10.3, 10.5_
  - _Boundary: AnalysisService, PatchRepository, CourseRepository_
  - _Depends: 6.2_

- [x] 6.4 Patch detail、stale 判定、Apply / Reject を実装する
  - Patch 取得時に proposed patch と current course markdown を比較し、必要なら `stale` に更新する。
  - Apply / Reject は transaction で `patch.status == proposed` と baseMarkdown 一致を確認する。
  - non-proposed patch は 409 `patch_not_proposed` と currentStatus を返す。
  - _Requirements: 7.6, 8.1, 8.2, 8.3, 8.5, 8.6, 9.4_
  - _Boundary: PatchService, PatchRepository, CourseRepository_
  - _Depends: 2.2, 2.4, 6.3_

- [x] 6.5 ownerFeedback と Patch decision response を実装する
  - Apply / Reject request の ownerFeedback を patch に保存する。
  - Apply 成功時は course markdown と version、patch status、appliedAt が更新される。
  - Reject 成功時は patch status が `rejected` になり、course markdown は変わらない。
  - _Requirements: 8.2, 8.3, 8.4, 9.4_
  - _Boundary: PatchService, PatchRepository_
  - _Depends: 6.4_

- [x] 6.6 Analysis / Patch backend の unit と integration test を追加する
  - analysis state transition、少数回答 confidenceNote、analysis failure、latestPatchId 更新を検証する。
  - stale patch、apply success、reject success、non-proposed 409、concurrent apply を検証する。
  - Patch が人間の Apply なしに course を更新しないことを確認する。
  - _Requirements: 6.1, 6.4, 7.6, 8.2, 8.3, 8.4, 8.5, 8.6, 9.4, 10.2, 10.3_
  - _Boundary: AnalysisService, PatchService_

- [x] 7. Owner frontend: Course、Drill、Analysis の画面を実装する
- [x] 7.1 Frontend API client と型を backend contract に合わせる
  - owner / learner API の request、response、error shape を TypeScript で表現する。
  - invalid token、validation error、status conflict、failed status を UI が判定できる。
  - typecheck で API 型の参照が通る。
  - _Requirements: 4.6, 8.6, 10.3, 10.5_
  - _Boundary: Frontend API client_

- [x] 7.2 (P) Course Editor を実装する
  - title と Markdown textarea、Save、Generate drill、latest drill、latest patch、機密資料を使わない前提の注意表示を出す。
  - 空 title、空 markdown、20,000 文字超過の validation error を表示する。
  - 保存後に再取得した course 内容と latest state が画面に表示される。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 9.3, 10.5_
  - _Boundary: CourseEditorPage_
  - _Depends: 7.1_

- [x] 7.3 (P) Drill Admin / Share Page を実装する
  - generated questions、rubric summary、share URL、answer count を表示する。
  - answer count が 1 件以上のとき Analyze Answers を開始できる。
  - generating / failed / ready の状態が StatusBanner で区別して表示される。
  - _Requirements: 2.6, 3.1, 3.2, 3.4, 3.5, 10.1, 10.3_
  - _Boundary: DrillAdminPage_
  - _Depends: 7.1_

- [x] 7.4 Analysis start と進行状態 UI を実装する
  - Analyze Answers 実行時に analyzing 状態を表示する。
  - no graded answers、drill_not_analyzable、analysis failed を再試行可能な表示にする。
  - analyzed 成功後に Patch Review へ遷移できる。
  - _Requirements: 6.1, 10.2, 10.3, 10.5_
  - _Boundary: DrillAdminPage, StatusBanner_
  - _Depends: 7.1, 7.3_

- [x] 7.5 Owner frontend の表示テストを追加する
  - Course validation、share URL 表示、answer count、analyze button、生成失敗表示を確認する。
  - 機密資料を使わない前提の注意表示が Course Editor に出ることを確認する。
  - typecheck と frontend test が通る。
  - _Requirements: 1.2, 1.3, 1.4, 2.6, 3.2, 3.4, 3.5, 9.3, 10.1, 10.3_
  - _Boundary: CourseEditorPage, DrillAdminPage_

- [x] 8. Learner and patch frontend: 回答フォームと Patch Review を実装する
- [x] 8.1 (P) Learner Drill Form を実装する
  - valid share URL で learnerName と 3 問の answer textarea を表示する。
  - learnerName / answerText の validation error と invalid share URL を表示する。
  - submit 成功時に提出完了と最小限の feedback を表示する。
  - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6_
  - _Boundary: LearnerDrillPage, AnswerForm_
  - _Depends: 7.1_

- [x] 8.2 Learner UI で非公開情報が出ないことを保証する
  - Learner Drill Form と submit result に rubric と idealAnswer を表示しない。
  - invalid token では drill content を表示しない。
  - UI test で非公開 field が render されないことを確認する。
  - _Requirements: 4.2, 9.1, 9.2_
  - _Boundary: LearnerDrillPage_
  - _Depends: 8.1_

- [x] 8.3 (P) Patch Review 画面を実装する
  - answer summary、average score、Failure Signal、patch summary、risk notes、diff、ownerFeedback を表示する。
  - sampleSize と confidenceNote がある Failure Signal を少数回答の傾向として表示する。
  - proposed / stale / applied / rejected status が画面で区別できる。
  - _Requirements: 6.2, 6.4, 7.2, 7.5, 8.1, 8.5_
  - _Boundary: PatchReviewPage, DiffViewer_
  - _Depends: 7.1_

- [x] 8.4 Patch Apply / Reject UI を実装する
  - ownerFeedback 入力後に Apply / Reject を実行できる。
  - stale patch では Apply を実行不可にし、再分析が必要であることを表示する。
  - 409 `patch_not_proposed` では currentStatus を表示する。
  - _Requirements: 8.2, 8.3, 8.4, 8.5, 8.6, 9.4_
  - _Boundary: PatchReviewPage, PatchActions_
  - _Depends: 8.3_

- [x] 8.5 Learner / Patch frontend の表示テストを追加する
  - valid answer submit、invalid token、empty fields、Patch stale、Apply/Reject success、409 conflict を確認する。
  - learner UI に rubric と idealAnswer が出ないことを確認する。
  - frontend test が通る。
  - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 8.2, 8.3, 8.4, 8.5, 8.6, 9.1, 9.2_

- [x] 9. Integration validation: 主要フローと横断品質を検証する
- [x] 9.1 Backend と frontend を実 API で接続する
  - frontend API client が backend routes と一致し、主要画面が mock なしで data を取得できる。
  - Course 作成から Drill Admin 表示までの local flow が動く。
  - API error が StatusBanner に変換される。
  - _Requirements: 1.1, 1.5, 3.1, 3.2, 10.3, 10.5_
  - _Depends: 4.5, 7.5_

- [x] 9.2 End-to-end MVP flow を通す
  - Course 保存、Drill 生成、share URL、Learner 回答、採点、分析、Patch Review、Apply までを一連で確認する。
  - Apply 後に course markdown と version が更新され、patch status が applied になる。
  - 受講者向け画面に非公開情報が出ないことを同じ flow 内で確認する。
  - _Requirements: 1.1, 2.1, 3.2, 4.1, 4.5, 5.1, 6.1, 7.1, 8.1, 8.2, 9.1, 9.4_
  - _Depends: 5.4, 6.6, 8.5, 9.1_

- [x] 9.3 Error and conflict flow を通す
  - invalid shareToken、grading failure、analysis failure、stale patch、non-proposed patch 409 を end-to-end で確認する。
  - すべての失敗が再試行可能または現在状態付きの UI 表示になる。
  - 不完全な Agent 結果が確定表示されないことを確認する。
  - _Requirements: 2.6, 4.6, 5.5, 8.5, 8.6, 10.3, 10.4_
  - _Depends: 9.2_

- [x] 9.4 Security boundary regression を確認する
  - learner API と learner UI に rubric / idealAnswer が含まれないことを API response と DOM の両方で確認する。
  - shareToken なし、無効 token、別 token で drill content が見えないことを確認する。
  - Agent invocation payload に Firestore path、Secret、admin token が含まれないことを test double で確認する。
  - _Requirements: 4.2, 4.6, 9.1, 9.2, 9.4_

- [x] 9.5 Observability and performance smoke を確認する
  - Agent task name、latency、validation error reason、courseId、drillRunId、patchId がログに出る。
  - learner answer 全文が通常ログに出ない。
  - 20,000 文字の course markdown で保存、生成、分析の smoke test が通る。
  - _Requirements: 1.4, 10.2, 10.3, 10.4, 10.5_

- [x] 9.6 Final build and test gate を整える
  - backend tests、frontend tests、typecheck、build を一つずつ実行できる。
  - 失敗時にどの境界の失敗か分かる command output になる。
  - 全 test gate が通った状態で実装完了を判定できる。
  - _Requirements: 10.3, 10.4_

## Implementation Notes

- 1.1: `uv run pytest` は PyPI 取得時の `invalid peer certificate: UnknownIssuer` で失敗するため、既存 venv での検証は `uv run --no-sync pytest` / `ruff` / `mypy` を使用した。
- 1.3: agent 側の `uv run` は `UV_NATIVE_TLS=true` と escalated access で依存解決できた。ADK import test は `BaseAgentConfig is deprecated` warning を出すが成功している。
