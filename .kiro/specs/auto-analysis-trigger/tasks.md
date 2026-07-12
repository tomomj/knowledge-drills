# Implementation Plan

- [ ] 1. 分析状態と判定基盤を整備する
- [x] 1.1 分析起動元、二重snapshot、二重watermarkの後方互換データ契約を追加する
  - 自動・手動の起動元、Agent入力件数、確定スコア件数、自動閾値専用watermark、ドリル固有patch IDを型安全に表現する。
  - 旧documentは起動元manual、専用watermark未記録、patch IDなしとして読み、既存のcamelCase契約を維持する。
  - 負の専用watermarkを拒否し、新旧documentのserialization round-tripをschema testで固定する。
  - 完了時に、auto/manualで異なるsnapshot集合を一つの件数へ混在させないデータ契約がテストから確認できる。
  - _Requirements: 1.3, 1.4, 2.2, 2.3, 4.3, 4.4, 5.1, 5.2, 5.4_

- [x] 1.2 確定スコアpredicateと後方互換watermark resolverを追加する
  - 自動分析の対象を採点済みかつ合計・最大スコアが確定し、最大スコアが正である回答に限定する。
  - 専用watermark、legacy watermark、両方未記録を区別し、比較可能な確定スコアbaselineを解決する。
  - 両field未記録ではbaseline不明を表す値を返し、status別の意味づけをこの境界へ持ち込まない。
  - スコア欠損、専用値、legacy fallback、両field未記録のunit testが成功する。
  - _Requirements: 1.3, 1.4, 2.2, 2.3, 4.5_

- [x] 1.3 既存要分析判定と対象ドリル5件判定へ共通policyを適用する
  - 既存の要分析判定は1件閾値、70%未満、status別規則を維持し、確定スコアwatermarkだけを共通resolverへ寄せる。
  - 対象ドリルの未分析数を同じeffective watermarkから算出し、自動起動閾値を固定5件にする。
  - resolverがbaseline不明を返した場合は、READYをbaseline 0、ANALYZEDを未分析0件として解釈する。
  - 判定ロジックをrepository非依存に保ち、既存serviceはread wrapperとして維持する。
  - 4件/5件、manual後の専用watermark、両field未記録のstatus別結果、legacy documentで既存要分析結果が変わらないことをunit testで確認できる。
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.3, 4.5_

- [x] 1.4 (P) InMemory transactionを複数documentのall-or-nothing境界へ強化する
  - transaction開始時のcopy-on-write snapshot、例外時rollback、成功時commitを実装する。
  - 全CRUDとqueryを同じ再入可能lockで保護し、callback途中の状態を別threadへ公開しない。
  - commit、故障注入rollback、別threadのCRUD待機が専用testで観測でき、Google Firestore側の契約は変わらない。
  - _Requirements: 2.3, 2.5, 2.6, 4.1_
  - _Boundary: InMemory transaction contract_

- [ ] 2. 共通の分析claimとtransactional lifecycleを実装する
- [x] 2.1 manual claimとorigin別snapshotを共通execution境界へ追加する
  - manual claimは既存の実行可否とowner境界を維持し、全GRADED回答をAgent入力として固定する。
  - 同じ回答集合からAgent入力件数と確定スコア件数を別々に記録し、自動条件でmanual実行を制限しない。
  - 同一drill documentのread/writeで二重claimを防ぎ、成功時にANALYZING、manual起動元、初期timeline、patch IDなしを保存する。
  - repository-level testで状態guard、二回目claimの競合、snapshot件数の分離が確認できる。
  - _Requirements: 2.2, 2.4, 3.4, 3.6, 4.4, 4.5, 5.2_

- [x] 2.2 自動起動条件と原子的auto claimを実装する
  - current version、未分析の確定スコア回答5件、既存要分析判定、非ANALYZING、同じ講座にレビュー待ちpatchなしを全read後に判定する。
  - autoは確定スコア回答だけをsnapshotとし、同一drillとcourse documentを競合点にする。
  - 条件不成立と既存状態競合はwriteなしの正常no-opとする。
  - repository-level testで各guard、二回目auto claimのno-op、成功時のautomatic起動元とsnapshotが確認できる。
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 2.2, 3.4, 3.5, 3.6, 3.7, 3.8, 5.1_

- [x] 2.3 patch作成あり・なしの成功終端をtransactionalにする
  - optional patch、ANALYZED、二重watermark、ドリル固有patch ID、course summaryを一括確定する。
  - Failure Signalなしはpatchなし成功として両watermarkを進め、後着回答をsnapshot件数へ含めない。
  - course versionがclaim時と一致する場合だけ成功終端を許可する。
  - 故障注入testでpatch・drill・courseの部分commitが残らず、patchあり/なしの永続結果が確認できる。
  - _Requirements: 2.3, 2.4, 2.5, 4.1, 4.2, 5.1, 5.2_

- [x] 2.4 分析進捗と通常失敗・stale version終端をtransactionalにする
  - 進捗更新ではnested transactionを開始せず、Agent呼出しやUUID生成などの副作用をtransaction外に保つ。
  - 通常例外とversion不一致ではREADY、failed timeline、patch IDなしを保存し、二重watermarkを更新しない。
  - 失敗後はmanual再実行可能な状態を維持し、自動retryを登録しない。
  - testで通常失敗、version不一致、watermark不変、manual再claim可能が確認できる。
  - _Requirements: 2.4, 2.6, 2.7, 2.8, 4.4, 4.5_

- [x] 2.5 既存分析workflowをclaim済みsnapshot executorへ移行する
  - Agentにはclaimで固定した回答IDだけを渡し、分析中に追加された回答を今回の集合へ混入させない。
  - manualの同期interface、owner認可、patch optional結果を維持し、auto固有の5件条件でmanual実行を制限しない。
  - autoは確定スコア回答のみ、manualはscore欠損を含む全GRADED回答を処理し、成功・見送り・失敗を共通終端へ渡す。
  - service testでauto/manualの入力差、Failure Signalなし、Agent例外、既存manual回帰が確認できる。
  - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1, 4.2, 4.4, 4.5_

- [x] 2.6 採点後に利用するbest-effort自動分析triggerと監査ログを追加する
  - drill IDからauto claimを試し、claim成功時だけsnapshot executorを一度呼び出す。
  - 条件不成立と競合は正常no-opとし、通常例外は採点responseへ伝播させない。
  - skipped、started、completed、failedを起動元・snapshot件数・安全なcourse/drill識別子とともに記録し、background最上位例外も捕捉する。
  - timer、即時retry、定期retry、起動時評価、patch解消時評価を追加せず、回答本文・Failure Signal詳細・credentialをlogへ含めない。
  - fake logger testで全4結果と機密情報非出力が観測できる。
  - _Requirements: 1.1, 1.5, 2.7, 2.8, 3.1, 3.2, 3.3, 3.8, 5.1_

- [ ] 3. Backendのroute・composition・管理APIへ統合する
- [x] 3.1 shared execution境界をapplication compositionへ接続する
  - shared storageから共通execution境界、manual分析service、自動triggerを構築して同じ状態へ接続する。
  - 既存manual APIのdependency取得と同期結果を維持する。
  - application構築testで全serviceが同じexecution境界を利用し、manual分析回帰が成功することを確認できる。
  - _Requirements: 3.5, 3.6, 4.4, 5.1, 5.2_

- [x] 3.2 current/legacy採点成功後にresponse後taskを登録する
  - current/legacy回答routeで採点済み回答の保存後にrequestごと1件だけbackground taskを登録する。
  - 採点失敗・validation失敗ではtaskを登録せず、taskの完了や失敗で返却済み採点結果を変更しない。
  - ASGI send順序を観測するfakeを使い、response body送信後にtaskが開始されることを確認する。
  - current/legacy両routeのtestから登録回数、非登録経路、採点response不変が観測できる。
  - _Requirements: 1.1, 2.1, 2.7, 2.8, 3.1, 3.2, 3.3_

- [x] 3.3 (P) Drill Admin APIへ起動元とドリル固有patch状態を公開する
  - drill管理responseへ分析起動元と当該drillの直近patch IDをmappingする。
  - 旧documentではmanual/patchなし、自動成功ではautomatic/patch ID、見送り・失敗ではpatchなしを返す。
  - service/API testでcamelCase値が確認でき、別drillのcourse最新patchを返さない。
  - _Requirements: 2.6, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Boundary: Drill Admin API_
  - _Depends: 1.1, 2.3_

- [ ] 4. 自動起動元と完了状態をowner UIへ統合する
- [x] 4.1 Frontend API契約と分析タイムラインの起動元表示を追加する
  - drillとpatchのtyped responseへ起動元とドリル固有patch IDを追加し、既存fixtureを後方互換値へ更新する。
  - automaticの場合だけ分析タイムラインへ「AI 自動分析」を表示し、manualまたは未指定では既存DOMを変えない。
  - component testとtypecheckでautomatic表示、manual非表示、既存manual操作の型契約が確認できる。
  - _Requirements: 4.2, 4.3, 5.2, 5.3, 5.4, 5.5_

- [x] 4.2 Drill Adminで自動分析pollingを開始し成功・見送りを終端する
  - manual stateと分離してpolling回数とpatch見送りを明示的に表現する。
  - automaticかつANALYZINGを1秒間隔で再取得し、ANALYZEDとドリル固有patch IDでは既存patch画面へ遷移する。
  - ANALYZEDかつpatch IDなしでは同画面に見送り完了を表示してpollingを停止する。
  - fake timer testで開始条件、正しいpatch遷移、見送り停止が確認できる。
  - _Requirements: 2.6, 4.3, 5.3, 5.4, 5.5_

- [x] 4.3 Drill Adminの失敗・timeout・cleanup状態を実装する
  - pollingを最大180回に制限し、unmount時にtimerを解除する。
  - failed timelineではpollingを止めてmanual再実行導線を有効にし、一時通信失敗では最後の表示を維持する。
  - 上限到達時はtimeoutと再読込操作を表示し、それ以降の自動取得を止める。
  - fake timer testで失敗、一時通信失敗、180回上限、unmount後に追加取得がないことを確認できる。
  - _Requirements: 2.6, 4.3, 4.4, 4.5, 5.3, 5.5_

- [x] 4.4 (P) Patch Reviewへ自動起動元を表示する
  - patchの起動元を既存タイムラインへ渡し、automatic patchだけに「AI 自動分析」を表示する。
  - 自動提案を画面から自動適用・却下せず、既存owner操作だけを提供する。
  - page testでautomatic表示とmanualの表示・apply/reject回帰が確認できる。
  - _Requirements: 4.2, 4.3, 5.4, 5.5_
  - _Boundary: PatchReviewPage_
  - _Depends: 4.1_

- [x] 5. (P) Cloud Runでresponse後のbest-effort分析へCPUを割り当てる
  - backend containerをinstance-based CPU allocationへ変更し、scale-to-zero設定は維持する。
  - process-local task、instance終了時の未回収ANALYZING、durable retryなしという運用境界をインフラ資料へ記録する。
  - format・validate・planで本機能の差分がbackend CPU設定だけで、resource replacement、IAM、queue、scheduler追加がないことを確認できる。
  - _Requirements: 2.1_
  - _Boundary: Cloud Run runtime_

- [ ] 6. 交差ケースとend-to-end回帰を検証する
- [x] 6.1 (P) 実競合とpatch completionのlinearizationを検証する
  - 実threadでauto/autoとmanual/autoを同時開始し、分析開始が高々1件になることを確認する。
  - patch completion先行ではclaim再評価後no-op、auto claim先行では開始済み分析を継続する順序を確認する。
  - repository-level guard testとは重複せず、実競合時のtransaction順序と最終永続状態だけを検証する。
  - 全競合testで重複patchや既存状態の破壊がないことを確認できる。
  - _Requirements: 1.2, 3.4, 3.5, 3.6, 3.7, 3.8_
  - _Boundary: Analysis concurrency integration_
  - _Depends: 2.2, 2.3, 2.4, 3.1_

- [x] 6.2 origin別snapshot集合と件数の交差ケースを固定する
  - manualで確定スコア4件とscore欠損1件を分析後、確定スコア5件追加でauto claimが成立することを検証する。
  - auto後のmanualとclaim後の追加回答で、origin固有の回答IDとAgent入力件数が開始時snapshotから変化しないことを検証する。
  - autoの5確定スコア＋1 score欠損とmanualの同一回答集合で、Agent入力件数と確定スコア件数が混用されないことを確認できる。
  - _Requirements: 1.2, 1.3, 1.4, 2.2, 2.3, 2.4, 4.4, 4.5_

- [x] 6.3 成功・見送り・失敗時の二重watermarkをorigin横断で検証する
  - auto/manualそれぞれの成功で既存Agent入力watermarkと専用確定スコアwatermarkが対応するsnapshotまで進むことを検証する。
  - Failure Signalなしでも両watermarkが進み、通常失敗とversion不一致では両方が不変になることを検証する。
  - originを切り替えた再分析でも各watermarkが単調非減少となり、異なる母集団の件数を相互に差し引かないことを確認できる。
  - _Requirements: 2.3, 2.4, 2.5, 2.6, 4.1, 4.4, 4.5, 5.1, 5.2_

- [x] 6.4 legacy fallbackとlazy初期化の回帰を固定する
  - 専用field欠損でlegacy countがある場合に、現在の確定スコア件数との小さい方をbaselineにすることを検証する。
  - 両field欠損のREADYはbaseline 0、ANALYZEDの読み取りは未分析0件となることを検証する。
  - legacy ANALYZEDへの新回答は保存前lazy初期化後に追加回答だけが差分となり、既存要分析判定の結果が変わらないことを確認できる。
  - _Requirements: 1.2, 1.3, 1.4, 2.3, 3.2, 4.5_

- [x] 6.5 (P) 自動提案と既存manual flowをbrowser E2Eで検証する
  - 4回答済みdemoへ5件目を投稿し、人間が分析ボタンを押さずに自動分析から正しいpatch reviewへ到達する。
  - 自動patchに「AI 自動分析」を表示し、教材変更は既存owner apply/reject操作まで待つことを確認する。
  - 1回答のmanual分析では自動表示がなく、patch作成・適用が従来どおり完走することを確認する。
  - 自動・手動の両E2Eが成功し、監視からAI提案、人間承認までの主要デモ経路を再現できる。
  - _Requirements: 1.1, 1.2, 2.6, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5_
  - _Boundary: Auto and manual browser integration_
  - _Depends: 3.2, 3.3, 4.3, 4.4_

- [ ] 6.6 (P) Backendの回帰・lint・型検査を完了する
  - manual分析、Failure Signalなし、patch作成、owner認可、current/legacy採点routeの既存testを含むBackend testを実行する。
  - Backend lintと型検査を実行し、新しいtransaction・background処理による回帰を解消する。
  - Backendの全自動検証が成功するか、外部環境依存の未実行項目と理由が明示された状態にする。
  - _Requirements: 1.1, 1.5, 2.5, 2.6, 2.7, 2.8, 3.1, 4.1, 4.2, 4.4, 5.1, 5.2_
  - _Boundary: Backend validation_
  - _Depends: 3.1, 3.2, 3.3, 6.1, 6.2, 6.3, 6.4_

- [ ] 6.7 (P) Frontendの回帰・lint・型検査・buildを完了する
  - automatic/manualのcomponent・page testを含むFrontend testを実行する。
  - Frontend lint、型検査、buildを実行し、有限pollingと起動元表示による回帰を解消する。
  - Frontendの全自動検証が成功するか、外部環境依存の未実行項目と理由が明示された状態にする。
  - _Requirements: 2.6, 4.2, 4.3, 4.4, 4.5, 5.2, 5.3, 5.4, 5.5_
  - _Boundary: Frontend validation_
  - _Depends: 4.3, 4.4, 6.5_
