# 技術検証: Responses でワークフローをホストする (ローカル、スタブ)

2026-11-15 実施。Azure には接続せず、決まった応答を返すスタブのモデルで確認した。

## 使ったパッケージ

| パッケージ | 版 |
|---|---|
| agent-framework-core | 1.26.0 |
| agent-framework-declarative | 1.5.1 |
| agent-framework-foundry | 1.16.2 |
| agent-framework-foundry-hosting | 1.0.0b261112 (プレリリース) |
| azure-ai-agentserver-responses | 2.4.0 |

## ファイル

| ファイル | 内容 |
|---|---|
| `consultation.yaml`、`main_declarative.py` | 宣言型 (YAML) のワークフロー: 案内 → フォーム → 発言 → `InvokeAzureAgent` |
| `main_code.py` | 同じ流れをコードで組んだもの (`WorkflowBuilder` + `AgentExecutor`) |
| `main_approval.py` | 通常のツールと承認が必要なツールを呼ぶエージェント (台本どおりに動くスタブ) |
| `main_v10.py` | 相談の流れ全体 (進行役 + 相談役、フォーム、承認、終了、アンケート)。V-10 の画面の検証に使った ([spikes/chat-ui](../chat-ui/README.md)) |

起動: `uv run python main_code.py` (localhost:8088 の `/responses`)。

## 結果

| ID | 結果 | 内容 |
|---|---|---|
| V-1 | ○ | ワークフローの入力待ちは `function_call` (名前 `request_info`、引数に要求の中身) として返り、`function_call_output` で再開できる。承認は `mcp_approval_request` として返り、`mcp_approval_response` で再開できる。 |
| V-4 | ○ | `BaseChatClient` (+ `FunctionInvocationLayer`) を継承したスタブで、ツールの呼び出しを含めて台本どおりに動かせる。ストリーミングでは `ResponseStream` を返す必要がある。 |
| V-8 | ○ | 入力待ちの要求に、種類 (`request_type`) と任意の情報 (`metadata`、フォームの JSON Schema など) を載せられる。YAML の `RequestExternalInput` でもコードでも同じ。 |
| V-9 (YAML) | × | `InvokeAzureAgent` はエージェントをストリーミングなしで呼び、最後の文章を 1 回だけ出力する。ツールの呼び出しと結果は外に出ない。ツールの承認をワークフローの入力待ちにする仕組みもない。 |
| V-9 (コード) | ○ | `AgentExecutor` なら、文章が少しずつ届き (`response.output_text.delta`)、ツールの呼び出しと結果 (`function_call` / `function_call_output`) と承認の要求 (`mcp_approval_request`) が外側のストリームに現れる。承認すると、ツールが実行されて結果が届き、エージェントの続きの文章が流れる。 |

## 分かった制約

- **YAML の式には .NET が必要**: Python 版でも、`=Local.userMessage` のような式の評価に .NET ランタイムと PowerFx が必要 (`PowerFx is not available (dotnet runtime not installed)`)。
- **YAML の型の許可**: 途中の状態の保存で、宣言型パッケージの内部の型 (`ActionComplete` など) が許可されておらず、保存に失敗する。許可する型の一覧に自分で加える必要がある。
- **利用者の発言も `function_call_output` で返す**: 入力待ちがあるときに通常の入力メッセージを送るとエラーになる (`Pending workflow replies cannot be mixed with new input`)。要求を解釈する関数からは、待ち受けの ID が見えないため、通常のメッセージを待ち受けへの返事に読み替えることもできない。
- **要求ごとに作り直す**: ワークフロー、実行部品、エージェント、クライアントに加えて、**ツール**も要求ごとに作り直す必要がある (使い回すと `Native workflow requests cannot share ...` で失敗する)。
- **ローカルでのセッション**: ローカルでは、最初の要求から本文の `agent_session_id` に同じ値を入れないと、2 回目以降で前回の状態が見つからない。Foundry 上では基盤のセッション ID が使われる。
- ローカルの状態は `~/.agentserver/` に保存される (`AGENTSERVER_STATE_ROOT` で変更できる)。
