# E2E シナリオ

対象: Knowledge Drill MVP

前提:

- 認証はない。
- backend は起動済みである。
- frontend は backend に接続できる状態で起動済みである。
- Agent は local invoker で代替され、ドリル生成、採点、分析、Patch 生成が同期で完了する。

## Scenario 1: 講座作成からドリル生成まで

目的:

講座オーナーが Markdown 講座を保存し、3 問のドリルを生成できることを確認する。

手順:

1. `/courses` を開く。
2. Title に任意の講座名を入力する。
3. Markdown に 1 文字以上、20,000 文字以下の Markdown を入力する。
4. Save を押す。
5. `保存しました。` が表示されることを確認する。
6. Generate drill を押す。
7. `/courses/:courseId/drill-runs/:drillRunId` に遷移することを確認する。

期待結果:

- Course が保存される。
- Drill Admin 画面に 3 問の question が表示される。
- Share URL が `/drills/:shareToken` 形式で表示される。
- rubric は admin 画面では表示される。

## Scenario 2: 受講者回答と minimal feedback

目的:

受講者が share URL から回答し、rubric と idealAnswer を見ずに提出できることを確認する。

手順:

1. Scenario 1 で表示された Share URL を開く。
2. Learner name を入力する。
3. 3 問すべてに回答を入力する。
4. Submit を押す。

期待結果:

- `提出が完了しました。` が表示される。
- feedback が表示される。
- learner 画面には `rubric` と `idealAnswer` が表示されない。
- 回答提出後、admin 画面の Answer count が 1 になる。

## Scenario 3: 回答分析と Document Patch 確認

目的:

講座オーナーが回答を分析し、Failure Signal と Document Patch diff を確認できることを確認する。

手順:

1. Scenario 2 の提出後、Drill Admin 画面を開く。
2. Analyze answers を押す。
3. Analysis & Patch Review 画面に遷移することを確認する。

期待結果:

- Patch status が `proposed` になる。
- Answer summary、Failure Signal、Patch summary、Risk notes、diff が表示される。
- owner feedback textarea が表示される。
- Apply と Reject が押せる状態である。

## Scenario 4: Patch Apply

目的:

講座オーナーが proposed patch を適用できることを確認する。

手順:

1. Scenario 3 の Patch Review 画面を開く。
2. Owner feedback を任意で入力する。
3. Apply を押す。

期待結果:

- Patch status が `applied` になる。
- Course markdown が patchedMarkdown に更新される。
- Course version が 1 増える。
- 同じ patch は再適用できない。

## Scenario 5: 無効な share token

目的:

無効な受講者 URL でドリル内容や採点情報が漏れないことを確認する。

手順:

1. `/drills/invalid-token` を開く。

期待結果:

- `共有 URL が無効です。` が表示される。
- question、rubric、idealAnswer は表示されない。

## Scenario 6: stale patch

目的:

Patch 生成後に course markdown が更新された場合、古い patch を apply できないことを確認する。

手順:

1. Scenario 3 まで進めて proposed patch を作成する。
2. Course Editor で同じ course の Markdown を更新する。
3. Patch Review 画面を再度開く。

期待結果:

- Patch status が `stale` になる。
- Apply が disabled になる。
- 再分析を促す warning が表示される。
