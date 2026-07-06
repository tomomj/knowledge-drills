# Requirements Document

## Project Description (Input)
実 Agent 接続: backend の LocalAgentInvoker スタブを、Google ADK 製の knowledge_drill_agent への実接続に置き換える。現状 backend/app/clients/local_agent_invoker.py がサンプル出力を返すだけのスタブになっており、これを ADK Runner の in-process 実行（または Agent Engine 経由）に差し替え、drill_generator_agent / grading_agent / failure_analysis_agent / document_patch_agent の実呼び出しを backend API から行えるようにする。Gemini API（Google Cloud AI）を実際に利用することが DevOps × AI Agent Hackathon 2026 の必須要件。出力の JSON 検証は backend 側の Pydantic 境界で行う方針。締切は 2026-07-10 のため、7/7 中の完了を目標とする最小構成でよい。

## Introduction

Knowledge Drills backend は現在、4つのエージェント操作（ドリル生成・回答採点・失敗分析・ドキュメントパッチ提案）をすべてスタブ（固定サンプル応答）で処理している。本フィーチャーは、これらの操作を実際の生成AI（Gemini API）を用いるエージェント呼び出しに置き換え、講座内容や受講者の回答に即した本物の生成・採点・分析結果を返せるようにする。DevOps × AI Agent Hackathon 2026 の必須要件（Google Cloud AI の実利用）を満たす基盤であり、締切（2026-07-10）から逆算した最小構成を対象とする。

**本スペックの位置づけ**: これは戦略（docs/hackathon-strategy.md）の勝ち筋本体ではなく、その前提となる Phase 0（土俵に乗るための基盤タスク）である。審査観点「Agent が価値の中心」への本命対応（failure_analysis_agent + document_patch_agent を自律型 improvement_agent へ統合する 4→3 エージェント化）は後続スペックで扱う。

## Boundary Context

- **In scope**: 4操作（ドリル生成・回答採点・失敗分析・パッチ提案）の実エージェント呼び出しへの置き換え、実行モードの設定（実接続／ローカルスタブの切り替え）、エージェント応答の検証とエラー応答、既存 API 契約の維持
- **Out of scope**: Firestore 実接続、Cloud Run へのデプロイと CI/CD、エージェント構成の再設計（improvement_agent への統合）、フロントエンドの変更、エージェント思考過程のストリーム表示
- **Adjacent expectations**: 4エージェントの定義（プロンプト・入出力スキーマ）は既存の agent パッケージが提供済みであることを前提とする。フロントエンドは既存 API の形式が変わらないことを期待する。後続の improvement_agent 統合スペックは、本スペックが確立する実エージェント呼び出し基盤（呼び出し経路・検証境界・モード切り替え）の上に構築されることを前提とする

## Requirements

### Requirement 1: 実エージェントによるドリル生成

**Objective:** As a 講座オーナー, I want ドリル生成が実際の生成AIエージェントで行われること, so that 講座内容に即した設問が得られる

#### Acceptance Criteria

1. When 講座オーナーがドリル生成を要求した時, the Knowledge Drills backend shall 固定サンプル応答ではなく生成AI（Gemini）によるドリル生成エージェントを呼び出して設問を生成する
2. When ドリル生成エージェントを呼び出す時, the Knowledge Drills backend shall 対象講座の Markdown 本文をエージェントへの入力として渡す
3. When ドリル生成エージェントが応答を返した時, the Knowledge Drills backend shall 応答が既存のドリル生成スキーマ（設問3問・各設問の採点基準を含む）に適合することを検証してから受講者に公開可能な状態にする

### Requirement 2: 実エージェントによる回答採点

**Objective:** As a 受講者, I want 自分の回答が実際の生成AIエージェントで採点されること, so that 回答内容に応じた妥当なスコアとフィードバックが得られる

#### Acceptance Criteria

1. When 受講者がドリル回答を送信した時, the Knowledge Drills backend shall 生成AIによる採点エージェントを呼び出し、回答内容に基づくスコアとフィードバックを返す
2. When 採点エージェントが応答を返した時, the Knowledge Drills backend shall スコアが設問の採点基準の範囲内であることを検証してから採点結果を保存・返却する
3. When 採点エージェントが応答を返した時, the Knowledge Drills backend shall 採点結果が採点対象の設問に対応していること（設問識別子の一致）を検証し、不一致の応答を採点結果として保存しない

### Requirement 3: 実エージェントによる失敗分析とパッチ提案

**Objective:** As a 講座オーナー, I want 受講者のつまずき分析と資料修正案の生成が実際の生成AIエージェントで行われること, so that 実データに基づく改善提案が得られる

#### Acceptance Criteria

1. When 講座オーナーが失敗分析を実行した時, the Knowledge Drills backend shall 生成AIによる失敗分析エージェントを呼び出し、採点履歴に基づく弱点シグナルを返す
2. When 失敗分析の結果に基づいてパッチ提案が要求された時, the Knowledge Drills backend shall 生成AIによるドキュメントパッチエージェントを呼び出し、講座 Markdown への修正案を返す

> **Note（後続スペックへの接続）**: 本要件は既存の2エージェント（失敗分析・パッチ提案）を現行構成のまま実接続するものである。戦略上の本命である自律型 improvement_agent への統合（4→3 エージェント化、docs/hackathon-strategy.md §1）は後続スペックで行い、その際に本要件の呼び出し経路が置き換え対象となる。

### Requirement 4: エージェント応答の検証とエラー応答

**Objective:** As a 運用者, I want エージェントの不正応答や外部サービス障害が安全に処理されること, so that 一部の失敗がアプリケーション全体の停止や不正データの保存につながらない

#### Acceptance Criteria

1. When エージェントの応答が期待スキーマに適合しない時, the Knowledge Drills backend shall 有限回数の範囲で呼び出しを再試行する（回数の具体値は設計で定める。再試行の対象は応答の検証失敗のみとする）
2. If 検証失敗が再試行を尽くしても解消しない場合、または呼び出しの実行自体（接続・認証・タイムアウト等）が失敗した場合, the Knowledge Drills backend shall 呼び出し元 API にサーバーエラーを返し、他の操作の処理は継続する
3. If 外部生成AIサービスへの接続・認証に失敗した場合, the Knowledge Drills backend shall 失敗内容をログに記録し、呼び出し元 API にサーバーエラーを返す
4. If エージェント呼び出しが設定されたタイムアウトを超過した場合, the Knowledge Drills backend shall 呼び出しを打ち切り、呼び出し元 API にサーバーエラーを返す
5. While エージェント呼び出しを処理している間, the Knowledge Drills backend shall 講座本文・回答内容などのペイロード内容をログへ出力しない

### Requirement 5: 実行モードの設定

**Objective:** As a 開発者・運用者, I want 実エージェント接続とローカルスタブを設定で切り替えられること, so that API キーなしのローカル開発・CI 実行と、本番相当の実接続運用を両立できる

#### Acceptance Criteria

1. The Knowledge Drills backend shall 使用する生成AIモデル名および認証に必要な情報を、コード変更なしに運用設定で指定できるものとする（設定方式の具体は設計で定める）
2. Where 実エージェント接続モードが有効な場合, the Knowledge Drills backend shall 4操作（ドリル生成・回答採点・失敗分析・パッチ提案）すべてを実エージェント呼び出しで処理する
3. Where ローカルスタブモードが選択された場合, the Knowledge Drills backend shall 従来どおり固定サンプル応答で4操作すべてを処理する
4. If 実エージェント接続モードが有効であるにもかかわらず必要な認証設定が欠落している場合, the Knowledge Drills backend shall 起動時に設定不備を明確に報告する

### Requirement 6: 既存 API 契約とテスト独立性の維持

**Objective:** As a 開発チーム, I want 既存の API 契約と自動テストが実接続導入後も維持されること, so that フロントエンドや CI に影響を与えずに移行できる

#### Acceptance Criteria

1. The Knowledge Drills backend shall 既存 API エンドポイントのリクエスト・レスポンス形式を変更せずに実エージェント接続へ移行する
2. When 既存および新規の自動テストを実行した時, the Knowledge Drills backend shall 外部生成AIサービスへの接続なしで全テストを成功させる
