---
name: frontend
description: React、Vite、TypeScript の MVP フロントエンドを実装またはレビューするときに使う。浅いディレクトリ構成、依存方向、API と UI の分離、明示的なページ状態、テストしやすい validation、ESLint import rule / dependency-cruiser / knip の導入判断を扱う。
---

# Frontend

## 目的

MVP のフロントエンドを、過剰設計にせず、テストしやすく、変更しやすい構造に保つ。リッチな architecture、global state、feature-sliced directory よりも、浅い構造と明示的なページ状態を優先する。

## MVP 構成

この repository では root に `frontend/`、`backend/`、`terraform/` を置く前提にする。フロントエンド作業では `frontend/` を project root として扱う。

既存アプリにより明確な規約がない場合は、`frontend/src/` 配下で次の構成を使う。

```text
frontend/
  src/
    app/          # router, app shell, providers
    pages/        # route component と page-level orchestration
    components/   # 再利用可能な presentational component
    api/          # HTTP client, request/response types
    lib/          # pure helper, validation, formatting
    test/         # fixtures, render helpers, API mocks
```

現在の task が明確に必要としていない限り、`features/`、`domain/`、global store、複雑な layered architecture を導入しない。

## 責務分離

- `pages/` は route workflow、API 呼び出し、local page state、submit handler を持つ。
- `components/` は再利用可能な表示部品にする。data は props で受け取り、user intent は callback で外へ出す。
- `api/` は HTTP 呼び出しと API request/response type を持つ。
- `lib/` は純粋な validation、formatting、state helper を持つ。`lib/` は React を import しない。
- `test/` は fixtures、render helper、mocked API response を持つ。

## 依存方向

許可する依存:

```text
pages -> api
pages -> components
pages -> lib
components -> lib
api -> lib
lib -> nothing
```

禁止する依存:

```text
components -> api
lib -> React
api -> pages
api -> components
circular imports
```

再利用 component が backend data を必要とする場合、component から `api/` を import せず、page から props で渡す。

## ページ状態

意味のある workflow state は明示的に表現する。状態が 3 つ以上になる場合は、散らばった boolean よりも page state union を優先する。

MVP でよく使う状態:

```text
idle
loading
ready
validationError
failed
stale
conflict
invalidToken
```

retry 可能な失敗は UI と test で確認できる状態にする。invalid token、stale patch、validation error、server failure を汎用 error に潰さない。

## テストしやすさ

- API 呼び出しは page level または `api/` に置き、再利用 component の中に置かない。
- 分岐を持つ business validation は `lib/` に出し、React render なしで直接 test できるようにする。
- API 依存 page は mocked API response で test する。
- 純粋な validation helper は直接 unit test する。
- render 中の隠れた side effect を避ける。
- MVP flow では、local page state で表現できない場合を除き global state library を追加しない。
- API state を持つ page を実装するときは、success、validation error、loading、server error の test を追加する。

## 依存関係チェック tooling

現在の構造を守るために、最も軽い tool から使う。`frontend/` scaffold 時は、少なくとも TypeScript typecheck と ESLint を実行できる状態にする。

1. まず TypeScript typecheck と ESLint を使う。
2. 明らかな禁止 import が少数なら ESLint `no-restricted-imports` を使う。例: `components -> api`。
3. import rule が増える、循環 import が出る、architecture drift を review で見つけにくくなった場合に `dependency-cruiser` を追加する。
4. 未使用 file、export、dependency が増え始めた場合に `knip` を追加する。

現在のディレクトリ構成より重い architecture tooling は導入しない。

推奨 dev dependency:

```text
eslint
dependency-cruiser
knip
```

推奨 npm scripts:

```json
{
  "typecheck": "tsc --noEmit",
  "lint": "eslint .",
  "depcheck": "depcruise src --validate .dependency-cruiser.cjs",
  "knip": "knip"
}
```

`dependency-cruiser` を追加する場合は、`components -> api`、`lib -> React`、`api -> pages/components`、circular imports を禁止する最小 config から始める。

## Knowledge Drill 固有ルール

この repository で作業する場合は次を守る。

- 受講者向け page に `rubric` や `idealAnswer` を表示しない。
- invalid share token、stale patch、patch conflict は明示的な page state として扱う。
- Course editor は empty title、empty markdown、20,000 文字上限を validation する。
- Drill admin は generating、ready、failed、analyzing、analyzed を区別する。
- Patch review は stale の場合に Apply 不可を表示し、`patch_not_proposed` conflict では current status を表示する。
- retry 可能な backend failure を generic error text に隠さない。

## 完了前チェック

フロントエンド作業の完了を主張する前に確認する。

- frontend typecheck があれば実行する。
- 変更した page、component、validation helper の frontend test があれば実行する。
- routing、bundling、shared type を変更した場合は frontend build を実行する。
- learner view に `rubric` や `idealAnswer` が表示されないことを確認する。
- mobile と desktop で明らかな text overflow や incoherent overlap がないことを確認する。
