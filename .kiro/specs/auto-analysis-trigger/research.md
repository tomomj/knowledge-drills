# Implementation Gap Analysis

## Analysis Scope

本分析は、承認済みの `auto-analysis-trigger` requirements と既存の Knowledge Drills 実装との差分を
調査し、design フェーズで選択すべき実装方針を整理する。対象は採点後の自動起動、既存要分析判定の再利用、
同一ドリルの重複防止、分析開始時 snapshot、起動元の記録と表示、および受講者レスポンスを待たせない
実行境界である。

`.kiro/steering/` は存在しないため、プロジェクト文脈は以下から取得した。

- `.kiro/specs/auto-analysis-trigger/requirements.md`
- `.kiro/specs/course-needs-analysis-badge/requirements.md`
- `.kiro/specs/failure-analysis-review-loop/requirements.md`
- `backend-fastapi` / `frontend` のローカル実装規約
- 現行 backend、frontend、Terraform、テストコード

## Analysis Summary

- 既存の採点、講座単位の要分析判定、分析パイプライン、パッチ見送り、失敗復帰、分析済み件数は再利用できる。
- 主な不足は、採点成功後の起動フック、対象ドリル専用の未分析3件判定、原子的な開始予約、厳密な開始時
  snapshot、起動元の永続化とUI表示である。
- 現行の `AnalysisService.start_analysis()` は状態確認と `ANALYZING` 更新が一つの原子的な予約ではないため、
  auto/auto および manual/auto の同時開始を防げない。
- frontend の既存タイムラインは失敗表示を再利用できるが、起動元のAPI型と「AI 自動分析」表示がない。
- 最大の設計論点はレスポンス後実行である。現行Cloud Run設定上、process-local background taskは
  best-effortであり、完走保証には永続queueが必要になる。ただしqueueの自動再配信は今回の
  「自動リトライなし」と調整が必要である。

## Current State

### Backend assets

| Existing asset | Current responsibility | Reuse potential |
|---|---|---|
| `backend/app/services/answer_service.py` | 回答保存、採点、`GRADED` 確定、score trend更新 | `GRADED` 保存後を評価契機として利用可能 |
| `backend/app/services/needs_analysis.py` | 現行version全体の要分析判定 | 既存警告条件としてそのまま再利用可能 |
| `backend/app/services/analysis_service.py` | 手動分析、timeline、Failure Signal判定、patch作成、成功/失敗状態 | 分析本体を再利用可能 |
| `DrillRun.analyzed_answer_count` | 成功した分析がAgentへ渡した回答件数 | manualはscore欠損を含むため自動閾値には比較不能 |
| `PatchRepository.list_by_course()` | 講座に属するpatchの列挙 | `PROPOSED` 抑止判定に利用可能 |
| `FirestoreClient.run_transaction()` | InMemory / Google共通transaction境界 | 同一drillの開始予約に利用可能 |
| `backend/app/main.py` | repository / service構築とapp state登録 | trigger coordinatorのDI追加先 |

既存の `needsAnalysis` は、講座の現行versionに属する全drill runを対象に、採点済み回答全体の
平均スコア率と未分析件数を集計する。一方、自動起動閾値の3件は回答が投稿された単一drillを対象とする。
したがって既存の `compute_needs_analysis()` の閾値・平均スコア・status規則は警告判定として再利用し、
対象drillの3件判定は別の小さなpure helperとして追加する。両方の未分析差分は比較可能な専用scored
watermarkを共有し、既存警告の1件閾値は変更しない。

既存分析はFailure Signalが0件ならpatchを作らず正常に `ANALYZED` となり、Agentへ渡した全`GRADED`件数を
`analyzed_answer_count` に保存する。自動閾値はscore確定回答だけを数えるため、このfieldをそのまま差し引くと
manual後に過少計上する。失敗時に件数を維持し、failed timelineと`error_message`を保存する終端契約は再利用できる。

### Frontend assets

| Existing asset | Current responsibility | Reuse potential |
|---|---|---|
| `AnalysisTimeline` | running/completed/failed/skippedの表示 | 自動分析失敗表示をそのまま再利用可能 |
| `DrillAdminPage` | timeline表示、手動分析、分析中polling | 起動元chipと自動分析状態の表示先 |
| `PatchReviewPage` | patch、timeline、apply/reject | 自動提案chipの表示先 |
| `frontend/src/api/types.ts` | backend response型 | optional起動元fieldの追加先 |

既存の手動分析中pollingは、画面内の手動POSTを起点としたlocal stateが `loading` の場合だけ動く。
自動分析中のdrillを後から開く場合、初回状態は表示できるが、その後の自動更新は行われない。自動分析中の
リアルタイム追従を今回含めるかはdesignで決める必要がある。requirementsは常時pollingを要求していない。

### Infrastructure assets

現行backend Cloud Runは `min_instance_count = 0`、`cpu_idle = true` である
（`terraform/main.tf:203-205,290-296`）。request-based CPUでscale-to-zeroするため、response送信後に
同一processで続ける長時間AI分析の完走は保証されない。

## Requirement-to-Asset Map

| Requirement capability | Existing asset | Gap |
|---|---|---|
| 採点成功時だけ評価 | `AnswerService.submit_answer()` の `GRADED` 保存 | **Missing**: route / serviceからtriggerへの接続 |
| 現行version判定 | `needs_analysis.py` | Reusable |
| 既存の要分析判定 | `evaluate_course_needs_analysis()` | Reusable |
| 対象drillの未分析3件 | 比較可能な既存watermarkなし | **Missing**: 専用scored watermarkとcount helper |
| 無効な回答の除外 | `_score_rate()` と既存テスト | Reusable |
| `PROPOSED` patch抑止 | `PatchRepository.list_by_course()` | **Missing**: 自動判定で未使用 |
| 受講者response非阻害 | 既存submitは同期処理のみ | **Missing / Constraint**: background実行境界 |
| 同一drill高々1件 | status guard | **Missing**: check→updateが原子的でない |
| 分析開始時snapshot | agent呼出直前のgraded answer取得 | **Constraint**: `ANALYZING` 更新後の再取得で隙間がある |
| Failure Signal 0件 | patchなし正常完了 | Reusable |
| 分析失敗 | READY復帰、件数維持、failed timeline | Reusable |
| 即時・定期retryなし | scheduler / retryなし | Reusable。ただしqueue採用時は要調整 |
| 起動元記録 | 該当fieldなし | **Missing** |
| timeline / patchへの起動元公開 | 既存responseと画面 | **Missing** |
| 人間のapply/reject | `PatchService` と既存画面 | Reusable |

## Detailed Gaps and Constraints

### 1. Trigger orchestration

`AnswerService` は採点ロジックを所有しており、分析条件、patch状態、分析実行まで直接持たせると責務が
肥大化する。採点成功後にdrill IDを渡せる小さな `AutoAnalysisTrigger` 相当のserviceを追加する方が、
既存の `routes -> services -> repositories` の依存方向に合う。

採点失敗経路ではtriggerを登録しない。一覧取得、patch apply/reject、application起動、定期pollingからも
triggerを呼ばない。

### 2. Same-drill claim

現行 `start_analysis()` はdrillを読み、状態を確認した後に通常更新する。二つのrequestが同じ `READY` を
読めるため、両方がagent実行へ進む可能性がある。manualとautoの両方を共通のtransactional claimへ通し、
transaction内で最新statusを読み直して一方だけを `ANALYZING` にする必要がある。

大規模なcourse leaseやgeneration fencingはrequirementsの範囲外である。今回必要なのは同一drillの
開始予約だけであり、既存 `FirestoreClient.run_transaction()` を使う局所的な拡張で実現可能である。

### 3. Analysis-start snapshot

現行実装は `ANALYZING` 保存後に回答を再取得するため、状態変更と取得の間に採点された回答が今回の分析へ
入る可能性がある。requirementsの「分析開始時点」を固定するには、claim時にorigin固有の回答集合
（autoは確定スコア回答、manualは全GRADED）のsnapshotを確定し、分析本体へ渡す必要がある。

候補は次の二つである。

- 回答ID一覧をclaim結果として渡す。対象が明確で、回答内容を再取得しても集合を固定できる。
- 採点済み回答object一覧をそのままexecutorへ渡す。process-local実行では最小だが、task再構築はできない。

snapshot countだけでは、どの回答をagentへ渡したかを再現できない。

### 4. Proposed patch race

既存 `PatchRepository.list_by_course()` で `PROPOSED` の有無を判定できる。通常ケースの抑止には十分だが、
別drillの分析完了と新しいauto claimが完全に同時の場合、単純な事前readだけでは競合が残る。
designではauto claimとpatch確定の双方を、同じcourse documentをread/writeするtransactionへ参加させる。
Firestoreのserializable isolationにより、patch確定が先にcommitした場合はclaimが再実行され、再読した
`PROPOSED` によって開始を抑止する。claimが先にcommitした場合は、そのlinearization pointではpatchが
存在しないため開始は有効とする。これは期限・heartbeatを持つcourse leaseではなく、既存course documentを
transaction競合点として使う局所的な整合性境界である。

### 5. Origin persistence

現行 `DrillRun`、`DocumentPatch`、`DrillAdminResponse` に起動元がない。現在のtimelineとpatchで
auto/manualを識別するだけなら、両entityに後方互換なoptional fieldを追加すれば足りる。旧documentは
field欠落をmanual相当として扱えば一括移行を避けられる。

全分析実行の履歴を保持する別 `AnalysisRun` entityは今回のrequirementsに不要である。

### 6. Background execution lifecycle

FastAPI `BackgroundTasks` はresponse送信後に同一processで処理を実行する軽量用途の仕組みである。
AI分析は複数の外部呼出しを含む長時間処理であり、現行Cloud Runのrequest-based CPUとscale-to-zeroでは
完走保証がない。

- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [Cloud Run billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
- [Cloud Run container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Cloud RunでCloud Tasksを実行](https://docs.cloud.google.com/run/docs/triggering/using-tasks)
- [Cloud Tasks overview](https://docs.cloud.google.com/tasks/docs/dual-overview)

`cpu_idle = false` はresponse後のCPUを利用可能にするが、instance停止時のtask喪失までは防がない。
Cloud Tasksは永続配送を提供する一方、at-least-onceと自動再配信を前提とするため、Requirements 2.7の
「即時・定期的な自動再実行を行わない」との意味をdesignで分離する必要がある。

## Implementation Options

### Option A: Existing servicesへ直接追加

`AnswerService` またはlearn routeへ条件評価とprocess-local background実行を追加し、
`AnalysisService.start_analysis()` だけをtransactional claimへ変更する。

**Advantages**

- 追加ファイルが少なく、短時間で実装できる。
- 既存analysis / failure / patch契約を最大限再利用できる。

**Trade-offs**

- 採点serviceまたはrouteに分析条件が混ざる。
- 条件評価、claim、background例外処理の単体テストが難しくなる。
- process-local taskの喪失リスクが残る。

**Estimated effort**: S–M（2–4日）  
**Risk**: Medium

### Option B: Durable task + AnalysisRun entity

永続task queueと実行entityを追加し、回答ID snapshot、origin、実行状態を保存してworkerが分析する。

**Advantages**

- process停止や再deployに強い。
- 実行履歴、snapshot、idempotencyを明示できる。

**Trade-offs**

- queue、IAM、worker endpoint、Terraform、retry設計が必要になる。
- at-least-once deliveryと「自動リトライなし」の整理が必要になる。
- 今回の分散実行・障害復旧基盤を強化しないという境界を超えやすい。

**Estimated effort**: M–L（5–10日）  
**Risk**: Medium–High

### Option C: Small trigger service + existing analysis（Hybrid）

新しい小さなtrigger serviceが、現行version、対象drillの未分析3件、既存needsAnalysis、PROPOSEDを評価する。
repositoryへ同一drillのtransactional claimを追加し、manual/autoが共通利用する。既存AnalysisServiceは
claimとexecutorに分け、process-local runnerまたはdesignで選択した実行境界からexecutorを呼ぶ。

**Advantages**

- 採点と分析判定の責務を分けながら、既存analysis本体を再利用できる。
- 条件ごとの単体テストと競合テストを分離できる。
- 将来queueへ変更してもtrigger / executor境界を維持できる。

**Trade-offs**

- Option Aより新しいinterfaceが一つ増える。
- process-local runnerを選ぶ場合は完走保証がない。
- claim後のprocess停止による `ANALYZING` 残留は今回のscopeでは回収されない。

**Estimated effort**: M（3–5日）  
**Risk**: Medium

## Frontend and E2E Impact

- `DrillAdmin` と `DocumentPatch` のAPI型へoptional起動元fieldを追加する。
- automaticの場合だけDrill timelineとPatch headerに「AI 自動分析」を表示する。
- manualまたはfield欠落時は追加表示を出さず、既存表示を維持する。
- 自動失敗済みdrillを初回GETした場合に、failed timelineと手動ボタンを確認するpage testを追加する。
- `frontend/e2e/ux-audit.spec.ts` は2回答済みdemoへ3件目を投稿した後、手動分析ボタンを押す現行契約を持つ。
  新仕様と直接競合するため、「3件目投稿 → 自動patch作成をpoll → Patch画面でAI自動分析表示」へ変更する。
- 1回答だけで手動分析する `knowledge-drill.spec.ts` / `llm-agent.spec.ts` は、閾値未満でmanual表示を維持する
  回帰テストとして利用できる。

## Test Coverage Needed

### Backend

- 対象drillの未分析2件ではno-op、3件目の採点成功で一度だけclaimする。
- 採点中、採点失敗、スコア未確定、旧versionを3件に含めない。
- `needsAnalysis=false`、`PROPOSED`あり、すでに`ANALYZING`の各条件で状態を変更しない。
- auto/autoおよびmanual/autoの競合でagent invocationが一回だけになる。
- claim後に追加された回答が今回のsnapshotと分析済み件数に入らない。
- Failure Signal 0件でpatchなし・snapshot消化済みとなる。
- auto failureでcount不変、failed timeline、即時retryなし、次の採点で再評価する。
- 起動元の永続化、API serialization、旧documentの後方互換を確認する。
- 採点responseがanalysis完了を待たないことを、実行境界のfakeで確認する。

### Frontend

- automatic timeline / patchだけに「AI 自動分析」を表示する。
- manual / field欠落時は既存表示のままにする。
- 自動失敗timelineを表示し、手動分析ボタンが利用可能である。
- patch apply/rejectが従来どおり動く。
- 3件目を使うauto E2Eと、1件でのmanual E2Eを分ける。

## Complexity and Risk

- **Overall effort**: M（3–7日）
- **Overall risk**: Medium
- **Reason**: 条件評価とUIは小さいが、同一drillの原子的claim、開始時snapshot、response後の実行寿命が
  新しい設計判断になる。

## Design Gates Resolved

1. Option Cのsmall trigger hybridを採用し、course leaseやmigrationは導入しない。
2. snapshotはclaim時のorigin固有回答ID集合、Agent入力件数、確定スコア件数で固定する。
3. 起動元は既存entityの後方互換fieldで追加し、別実行履歴entityを作らない。
4. process-local best-effortと`cpu_idle=false`を採用し、infrastructure interruption後の回収は境界外とする。
5. `PROPOSED`条件はcourse documentを共通transaction競合点とするclaim linearizationで保証する。
6. pure判定をrepository非依存policyへ分離して循環依存を避ける。
7. `ux-audit.spec.ts`の3件目をauto E2Eへ更新し、既存1件シナリオをmanual回帰として残す。

---

## Design Discovery and Synthesis

### Summary

- **Feature**: `auto-analysis-trigger`
- **Discovery Scope**: Extension / integration-focused light discovery
- **Key Findings**:
  - auto claimとpatch確定は既存course documentを共通のtransaction競合点として直列化できる。
  - process-local background実行は最小構成だが、process停止・再deploy時の回収は保証できない。
  - 起動元は既存`DrillRun` / `DocumentPatch`の後方互換fieldで表現でき、データ移行は不要である。

### Research Log

#### Firestore transactionによるPROPOSED判定の原子化

- **Context**: Requirements 3.7と、別drillのpatch確定が同時に進む場合の競合を解消する必要がある。
- **Sources Consulted**:
  - [Firestore transaction isolation](https://firebase.google.com/docs/firestore/transaction-data-contention)
  - [Firestore transactions](https://firebase.google.com/docs/firestore/manage-data/transactions)
  - [Python Transaction API](https://docs.cloud.google.com/python/docs/reference/firestore/latest/google.cloud.firestore_v1.transaction.Transaction)
- **Findings**:
  - 同じcourse documentを双方がread/writeすればcommit-time serializable isolationにより競合側が再実行される。
  - document/queryを含む全readはwrite前に行い、callback内にAgent呼出しなどの副作用を置かない。
  - `Transaction.get`はdocument referenceとqueryを扱える。
- **Implications**: auto claimをlinearization pointとし、patch確定・course summary・drill終端を一つの
  transactionへ移す。course leaseや新collectionは作らない。

#### Process-local background lifecycle

- **Context**: Requirements 2.1を満たしつつ、分散queueを追加しない最小構成が必要である。
- **Sources Consulted**:
  - [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)
  - [Cloud Run billing settings](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
  - [Cloud Run container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- **Findings**:
  - `BackgroundTasks`はresponse送信後に同じapp processで実行される。
  - Cloud Runでresponse後もCPUを使うにはinstance-based billingが必要である。
  - instance-based billingでもprocess終了時の完走・回収は保証されない。
- **Implications**: backendの`cpu_idle`をfalseへ変更し、process停止時の回収と残留`ANALYZING`復旧は
  requirementsのOut of scopeとして明記する。Cloud Tasksは採用しない。

### Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Decision |
|---|---|---|---|---|
| Existing service extension | AnswerServiceへ判定と実行を直接追加 | ファイル数が少ない | 採点責務が肥大化する | 不採用 |
| Durable task | Cloud TasksとAnalysisRunを追加 | 実行喪失に強い | scope・IAM・retry設計が増える | 不採用 |
| Small trigger hybrid | 小さなtrigger、共通claim、既存AnalysisServiceを組み合わせる | 境界が明確で既存本体を再利用 | process停止回収はしない | 採用 |

### Design Decisions

#### Decision: course documentを整合性の競合点にする

- **Context**: `PROPOSED` patchが存在する間のauto claimを原子的に抑止する。
- **Alternatives Considered**: course lease、新guard collection、事前readのみ。
- **Selected Approach**: auto claimと全analysis completionが同じcourse documentをtransaction内でread/writeし、
  claim retry時に`PROPOSED`を再評価する。
- **Rationale**: 新しい永続entityやmigrationなしで、既存Firestore transaction境界を利用できる。
- **Trade-offs**: claimより後にpatchが確定しても開始済みanalysisは取り消さない。異なるdrillの同時分析自体は
  禁止しない。
- **Follow-up**: completionからnested transactionを呼ばず、全read-before-writeとcallback副作用禁止をtestする。

#### Decision: process-local best-effortを採用する

- **Context**: 受講者responseを待たせず、期限内に最小構成で自動提案を実現する。
- **Alternatives Considered**: synchronous分析、Cloud Tasks、process-local background。
- **Selected Approach**: FastAPI `BackgroundTasks`でresponse後にtriggerと分析を実行し、Cloud Runは
  `cpu_idle=false`にする。
- **Rationale**: 新しいqueue、endpoint、IAM、retry policyを追加せず、既存app processを再利用できる。
- **Trade-offs**: process停止・instance終了・再deploy時に実行が失われ、`ANALYZING`が残る可能性がある。
- **Follow-up**: この制約をrequirements、design、運用ログ、test境界で一貫させる。

#### Decision: generalizeするのは共通claim interfaceだけ

- **Context**: auto/autoとmanual/autoの重複を同じ規則で防ぐ必要がある。
- **Selected Approach**: `claim_manual_analysis`と`claim_auto_analysis`を同一repository boundaryに置き、
  auto固有条件だけをauto interfaceへ閉じ込める。
- **Rationale**: 大規模な実行履歴entityや汎用workflow engineを作らず、必要なinterfaceだけを共有できる。
- **Trade-offs**: infrastructure interruption後の再claimやfencingは持たない。

#### Decision: needs-analysisのpure policyをrepository非依存moduleへ分離する

- **Context**: transaction coordinatorがcourse snapshotを判定するとき、現行`services/needs_analysis.py`を
  repositoryから参照すると循環依存になる。
- **Selected Approach**: `backend/app/analysis_policy.py`へrepository非依存のcourse判定と対象drill未分析件数を
  置き、既存service wrapperとexecution repositoryが同じpure policyを利用する。
- **Rationale**: `schemas -> analysis policy -> repositories -> services`の一方向依存を維持できる。
- **Trade-offs**: 新規fileが一つ増えるが、判定ロジックの二重実装を避けられる。
- **Follow-up**: statusだけでなく`total_score` / `max_score`の存在と正値を検証する共通predicateを、
  起動閾値、snapshot、watermarkで共有する。

#### Decision: InMemory transactionにもall-or-nothing契約を持たせる

- **Context**: local/test既定storageの`run_transaction`はlockだけで、callback途中のwriteを例外時に戻せない。
- **Selected Approach**: transaction開始時に全collectionをcopy-on-write snapshotし、例外時に復元する。
  全CRUDも同じ再入可能lockで直列化する。
- **Rationale**: patch、drill、courseの複数document更新について、FirestoreとInMemoryで同じ原子性を検証できる。
- **Trade-offs**: test向け全collection copyのコストを許容し、Firestoreの競合retryまでは模倣しない。

#### Decision: autoとmanualの回答predicateを分離する

- **Context**: 既存manual分析は`status == GRADED`の全回答を利用する一方、自動起動には確定scoreが必要である。
- **Selected Approach**: auto claimだけが`is_scored_answer`をAgent入力に使い、manual claimは現行のstatus条件を
  維持する。Agent入力件数と、origin共通の確定スコアsnapshot件数をclaimへ別々に保持する。
- **Rationale**: 自動起動の厳密な閾値判定と既存manual契約の後方互換性を両立する。
- **Trade-offs**: predicateは意図的に統一せず、二つの件数を混用しない回帰testを必須にする。

#### Decision: 自動閾値専用の確定スコアwatermarkを追加する

- **Context**: manualの全GRADED件数とautoの確定スコア件数は母集団が異なり、既存
  `analyzedAnswerCount`一つへ保存すると未分析3件を過少計上する。
- **Alternatives Considered**: 既存watermarkを両originで共有する、manualのAgent入力を確定スコアだけへ狭める、
  自動閾値専用watermarkを追加する。
- **Selected Approach**: 既存`analyzedAnswerCount`の意味を維持し、DrillRunへ
  `autoAnalyzedScoredAnswerCount`を追加する。manual/auto両方の成功時に、claim時点の
  `is_scored_answer`総数まで単調に進める。失敗時は進めない。対象drillの3件判定と既存
  `compute_needs_analysis`の未分析差分は同じeffective watermarkを利用する。
- **Rationale**: manualの後方互換性を保ちつつ、自動閾値を常に同じ確定スコア母集団で比較できる。
- **Compatibility**: 専用field欠損時の`scored - min(legacy, scored)`は、現行の
  `max(0, scored - legacy)`と同値である。したがってlegacy documentの`needsAnalysis`結果は変えず、
  新しい分析成功後だけ専用fieldによって母集団不一致を解消する。
- **Trade-offs**: 後方互換fieldが一つ増える。field欠落/nullでは
  `min(analyzedAnswerCount, current scored count)`を暫定baselineとする。両field欠落ではbaseline不明を
  `None`で表し、READYは0、ANALYZEDは未分析0件とする。
  過去のscored集合はcountだけから完全復元できないため近似だが、単純0より既存回答の再計上を抑えられる。
  migrationは行わず、次の分析成功後は正確な専用fieldだけを使う。
- **Follow-up**: 「確定スコア2件＋score欠損1件」のmanual成功後に確定スコア3件を追加し、
  専用watermark 4との差分5でautoが起動する交差testを追加する。

#### Decision: drill固有patch IDと有限pollingで自動分析完了を扱う

- **Context**: course summaryのlatest patchは別drill由来になり得て、statusだけでは自動分析後の遷移先が決まらない。
- **Selected Approach**: `DrillRun` / `DrillAdminResponse`へ後方互換な`latestPatchId`を追加し、
  Drill Adminは1秒間隔・最大180回だけpollingする。patch作成時は既存patch画面へ遷移し、no-patch、failure、
  timeoutは同画面でそれぞれ終端表示する。
- **Rationale**: 新endpointなしで、対象drillが生成したpatchへ正確に到達し、無限pollingを防げる。
- **Trade-offs**: infrastructure interruptionで`ANALYZING`が残る問題自体は回収せず、UIはtimeoutとして扱う。

### Risks & Mitigations

- process停止で`ANALYZING`が残る — Out of scopeを明記し、通常例外だけはfail transactionでREADYへ戻す。
- transaction retryで副作用が重複する — UUID、時刻、Agent呼出しはcallback外で確定する。
- InMemoryの部分更新が残る — copy-on-write rollbackと全CRUD共通lockを実装し、故障注入testで確認する。
- auto用score predicateがmanual回答を除外する — manualはstatus-only predicateを維持し、origin別に回帰testする。
- origin別の回答件数が同一watermarkで比較不能になる — Agent入力件数と自動閾値専用scored watermarkを分離し、
  manual/auto双方の成功時に同じscored母集団で進める。
- 専用field欠損のlegacy runで既存回答を全件再計上する — 既存countと現在のscored件数の小さい方を
  fallbackにする。両field欠損のANALYZEDは現行どおり未分析0件とし、READYだけ0 baselineにする。
- 自動分析後にpatchへ到達できない／無限pollingになる — drill固有`latestPatchId`と180回上限を使う。
- 旧documentに起動元fieldがない — schema defaultを`manual`にして無移行で読む。
- 既存E2Eの3件目がauto起動と競合する — `ux-audit.spec.ts`をauto flowへ更新する。
