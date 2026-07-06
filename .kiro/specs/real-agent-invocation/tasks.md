# Implementation Plan

- [ ] 1. Foundation: 依存関係と実行モード設定の確立
- [x] 1.1 backend に ADK ランタイムと agent パッケージへの参照を追加する
  - backend の依存関係に google-adk（agent/uv.lock と同系の 2.x に固定）を追加し、agent パッケージをパス依存（editable）として参照できるようにする
  - google-cloud-aiplatform との依存解決が成立することをロックファイル更新で確認する
  - 依存リストを検証する既存テスト（test_runtime_dependencies）を新しい依存構成に合わせて更新する
  - 完了条件: backend の実行環境で knowledge_drill_agent と google.adk が import でき、既存テストが成功する
  - _Requirements: 5.2_

- [x] 1.2 (P) 実行モードとタイムアウトの運用設定を追加する
  - Settings に実行モード（local / adk、既定 local）とエージェント呼び出しタイムアウト秒（既定 60）を追加する
  - 既存の KNOWLEDGE_DRILLS_ prefix の環境変数で上書きできること
  - 完了条件: 既定値と環境変数上書きを検証するユニットテストが成功する
  - _Requirements: 5.1, 5.3_
  - _Boundary: Settings_

- [ ] 2. Core: ADK 実接続アダプタの実装
- [x] 2.1 リーフエージェントを個別実行するための前提を検証・整備する
  - リーフエージェント4つが root_agent の sub_agents 登録（単一親制約）のままで個別 Runner 実行できるかを検証する
  - 衝突する場合のみ agent パッケージにスタンドアロンのリーフエージェント生成ファクトリを追加する（プロンプト・入出力スキーマの内容は変更しない。境界を越える変更はこのタスクに限定する）
  - agent パッケージ側の既存契約テストが引き続き成功する
  - 検証は Runner 構築・実行経路の確認までとし、外部生成AIサービスへの接続は行わない
  - スタンドアロン生成ファクトリを追加する場合もモデル名をコードに固定せず、既存の運用設定（KNOWLEDGE_DRILL_AGENT_MODEL）が ADK 実行経路でも維持されることを確認する
  - 完了条件: backend から4リーフエージェントを個別に Runner へ搭載して実行経路に乗せられること、および環境変数で指定したモデル名が実行対象エージェントに反映されることを確認する検証テストが成功する
  - _Requirements: 5.1, 5.2_
  - _Boundary: AdkAgentInvoker, agent package_
  - _Depends: 1.1_

- [ ] 2.2 タスク名からリーフエージェントへの決定的マッピングと1回実行を実装する
  - 4つのリーフエージェントそれぞれに Runner を起動時構築し再利用する（共有 InMemorySessionService、root_agent 経由の転送は使わない）
  - テスト注入点として Runner 群のファクトリを差し替え可能にする
  - ペイロードを JSON 文字列のユーザーメッセージとして渡し、最終応答テキストを dict にして返す（スキーマ検証は行わず AgentRuntimeClient に委ねる）
  - 完了条件: フェイク Runner を注入したユニットテストで、4つのタスク名すべてが対応するエージェント実行にマッピングされ応答 dict が返る
  - _Requirements: 1.1, 1.2, 2.1, 3.1, 3.2, 5.2_

- [ ] 2.3 実行失敗の正規化とタイムアウトを実装する
  - 同期プロトコルを維持したまま呼び出し全体を設定されたタイムアウトで打ち切る（asyncio.run + wait_for）
  - 接続・認証エラー、タイムアウト、最終応答欠落、JSON パース不能をすべて AgentInvocationError に変換する（再試行しない）
  - ログにはタスク名・例外種別のみ記録し、ペイロード内容（講座本文・回答）を出力しない
  - 完了条件: タイムアウト・最終応答欠落・JSON パース不能・接続/認証エラーのそれぞれが AgentInvocationError に変換されるユニットテストが成功する
  - _Requirements: 4.3, 4.4, 4.5_
  - _Depends: 1.2_

- [ ] 2.4 実接続モードの起動時認証検証と設定の受け渡しを実装する
  - invoker 生成ファクトリで認証設定（AI Studio モードの API キー、または Vertex AI モードの変数一式）の欠落を検出する
  - 欠落時は欠落している変数名を明示した例外で起動を失敗させる
  - ファクトリが Settings のタイムアウト秒を invoker の生成時に受け渡す（タイムアウト配線の所有はこのタスク）
  - 完了条件: API キーなし・Vertex 変数不足の各パターンで欠落変数名を含むエラーになり、設定したタイムアウト値が invoker に伝わることを検証するユニットテストが成功する
  - _Requirements: 5.4_
  - _Depends: 1.2_

- [ ] 3. 検証境界の強化
- [ ] 3.1 (P) 採点応答の文脈整合性検証を追加する
  - 検証境界の共通処理に任意の事後検証フックを追加する（既定は従来どおり）
  - 採点では応答の questionId がリクエストの設問 ID と一致し、score が設問の max_score 以下であることを検証する
  - 違反はスキーマ不適合と同じ扱いで有限回再試行し、解消しなければ AgentInvocationError とする（不一致応答は保存されない）
  - 完了条件: 不一致/超過応答が再試行される・2回目成功で回復する・2回失敗でエラーになるユニットテストが成功する
  - _Requirements: 2.2, 2.3, 4.1_
  - _Boundary: AgentRuntimeClient_

- [ ] 3.2 (P) エージェント呼び出し失敗の HTTP エラー応答を追加する
  - AgentInvocationError を 502 agent_invocation_failed の ErrorResponse に変換する専用ハンドラを登録する
  - エラーメッセージ・ログにペイロード内容を含めない
  - 完了条件: AgentInvocationError を送出するフェイク invoker を注入した API 呼び出しが 502 を返し、後続リクエストが正常処理される統合テストが成功する
  - _Requirements: 4.2, 4.3_
  - _Boundary: ErrorHandler_

- [ ] 4. 統合: 配線と実行方式の切り替え
- [ ] 4.1 設定による invoker 選択を配線する
  - アプリ起動時に実行モードが adk なら認証検証付きファクトリで実接続 invoker を、それ以外は従来のスタブを注入する
  - 完了条件: 既定（local）の create_app で既存の全操作フローが従来どおり成功し、adk モード + 認証欠落で起動が明確に失敗する統合テストが成功する
  - _Depends: 1.2, 2.4_
  - _Requirements: 5.2, 5.3, 5.4_

- [ ] 4.2 (P) エージェント到達ルート5関数をスレッドプール実行に切り替える
  - design.md の Routes def 化一覧の5関数（generate_drill / analyze_course_drill / analyze_drill / submit_answer / submit_answer_legacy）を async def から def に変更する
  - legacy ルートは委譲の await を外して同期呼び出しにする（両関数の同時変更が必須）
  - 完了条件: ルート定義に対象5関数の async def が残っておらず（grep 検証）、await submit_answer が0件で、既存のルートテストが全て成功する
  - _Requirements: 4.2, 6.1_
  - _Boundary: Routes_

- [ ] 5. 検証
- [ ] 5.1 回帰テストと契約テストの全体実行
  - 認証系環境変数を未設定にした状態で backend / agent の全テストスイートが成功することを確認する（外部接続なし）
  - 既存契約テスト（sample_outputs とスキーマ互換）と lint / typecheck が成功する
  - 完了条件: uv run pytest（backend, agent）・ruff・mypy がすべて成功する
  - _Requirements: 1.3, 6.1, 6.2_

- [ ] 5.2 実 Gemini での手動スモークスクリプトを追加し、提出前に実行する
  - 実 API キー設定時に、ドリル生成→採点→失敗分析→パッチ提案の4操作を1周させる手動実行スクリプトを追加する（CI には含めない）
  - 要件 1.1 / 2.1 / 3.1 / 3.2 の「実エージェント呼び出し」を確認する唯一の実外部接続タスクのため必須とする。実キーがない環境ではスクリプト追加と手順確認までを行い、ハッカソン提出前に実キー環境で必ず手動実行して結果を記録する
  - 完了条件: スクリプトと手動実行手順が存在し、実キー環境での4操作1周の成功結果（実行ログまたは記録）が残っている
  - _Depends: 4.1_
  - _Requirements: 1.1, 2.1, 3.1, 3.2_

## Implementation Notes

- 1.1: この環境では `uv lock` / `uv sync` に `--native-tls` が必要（社内プロキシの TLS 証明書のため）。`uv run --frozen` は影響なし。google-adk 2.3.0 + google-cloud-aiplatform 1.159.0 で解決済み。
- 2.1: 単一親制約は Runner 構築ではなく実行経路汚染（AutoFlow の transfer_to_agent 注入）として衝突 → agent パッケージに create_*_agent ファクトリ4つを追加（プロンプト・スキーマ逐語不変）。2.2 はこのファクトリを使うこと。
- 2.1: ADK 2.3.0 では input_schema がユーザーメッセージに強制される（research.md の「強制されない」は古い）→ 2.2 のペイロードはスキーマ準拠 JSON 文字列必須。backend/pyproject.toml に mypy_path="../agent" 追加済み。
