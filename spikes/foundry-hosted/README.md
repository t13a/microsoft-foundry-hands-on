# 技術検証: Foundry 上での検証 (V-2、V-3、V-5、V-6、V-7)

2026-11-15 実施。`consultation-workflow/` は `azd ai agent init` (サンプル「Workflow agent (Responses, Agent Framework, Python)」) で作った azd のプロジェクトで、中身を `spikes/responses-workflow/main_v3.py` (相談の流れ全体 + Foundry のプロンプト エージェント) に差し替えたもの。

## 作ったリソース

| リソース | 名前 / 設定 |
|---|---|
| リソースグループ | `rg-consultation-workflow-dev-a0f264e2` (Japan East、azd が自動で命名) |
| Foundry アカウント / プロジェクト | `cog-oyhg7a6qqpz6e` / `ai-project-demo-city` |
| モデル デプロイ | `gpt-5-mini` (2025-08-07、Global Standard、容量 10) |
| プロンプト エージェント | `search-assistant` (`spikes/responses-workflow/create_prompt_agent.py` で作成) |
| ホスト型エージェント | `consultation-workflow` (コード デプロイ、0.5 vCPU / 1 GiB) |
| 監視 | Log Analytics、Application Insights (プロジェクトに接続済み) |

Container Registry は作られなかった (コード デプロイはソースを送ってリモートでビルドする)。

## 手順

```bash
cd consultation-workflow
azd env set AZURE_SUBSCRIPTION_ID <id>; azd env set AZURE_LOCATION japaneast
azd env set AZURE_AI_PROJECT_NAME ai-project-demo-city
azd provision --no-prompt                     # 約 3 分半
# プロンプト エージェント (要: Foundry User ロール)
FOUNDRY_PROJECT_ENDPOINT=... uv run python ../../responses-workflow/create_prompt_agent.py gpt-5-mini
azd deploy --no-prompt                        # 約 1 分 45 秒
# 相談を最後まで通す (Entra ID のトークンを付ける)
cd ../../responses-workflow
uv run python drive.py https://<account>.services.ai.azure.com/api/projects/<project>/agents/consultation-workflow/endpoint/protocols/openai --token
```

## 結果

| ID | 結果 | 内容 |
|---|---|---|
| V-2 | △ | 利用者のトークン (対象 `https://ai.azure.com/.default`) で、デプロイしたホスト型エージェントの Responses の受け口を呼び、相談を最後まで通せた。マネージド ID からの呼び出しと BFF での中継は未確認 (BFF を Container Apps に置く段階で確認する)。 |
| V-3 | ○ | `FoundryAgent` でプロンプト エージェントを名前だけ (版の指定なし) で呼び出せた。Foundry 側のツール定義とローカルの関数の実装が結びつき、承認つきのツール (`propose_display`、`propose_end`) も動いた。担当外の質問 (天気) を丁寧に断った。 |
| V-5 | ○ (一部) | 要求ごとに別のトレースになるが、全スパンにセッション ID (`microsoft.session.id`) が付き、相談単位でまとめられる。モデルの入出力の中身 (`gen_ai.input.messages` / `gen_ai.output.messages`) も記録される。ポータルの会話の画面と継続評価は未確認。 |
| V-6 | 遮断された | 自殺をほのめかす発言はコンテンツフィルターで遮断され (`finish_reason: content_filter`)、英語の定型文 ("I'm sorry, but I cannot assist with that request.") が返り、応答は未完了 (`incomplete`) になった。 |
| V-7 | △ | Container Registry は不要だった。課金額は反映待ち (1〜2 日後に Cost Management で確認する)。 |

## 計測値

| 項目 | 値 |
|---|---|
| 応答の開始まで (初回、コンテナーの起動あり) | 約 8.7 秒 (うちコンテナーの準備 約 5 秒) |
| 応答の開始まで (2 回目以降) | 約 1.3〜1.7 秒 |
| 1 回のやり取りの所要時間 | 約 5〜20 秒 (ツール呼び出しの回数による) |
| 1 回の相談のトークン (発言 3 回) | 入力 約 10,800 (うちキャッシュ 約 3,200)、出力 約 2,300 |

## 分かったこと (対処が必要なもの)

- **`gpt-6-luna` などの新しいモデルはクォータが 0**: どのリージョンでもクォータがなく、デプロイできなかった。クォータがあった `gpt-5-mini` を使った。
- **Foundry User ロールが必要**: サブスクリプションの所有者でも、エージェントの作成にはデータ操作用のロール (Foundry User) が別に必要。割り当ての反映に数分かかった。
- **プロンプト エージェントに `store=False` が必要**: ワークフローのホストが会話の履歴を持つため、中のエージェントに保存しない指定を求められる。
- **continuation token の問題 (プレリリース版の組み合わせ)**: OpenAI の Responses クライアントは、ストリーミング中の更新に続きから再開するための目印 (continuation token) を付ける。ワークフローのホストはこれを「チェックポイントを保存できない応答」とみなして拒否する。エージェントのミドルウェアで目印を外して回避した (`main.py` の `drop_continuation_tokens`)。
- **Foundry のエンドポイントは null を受け付けない**: 1 回目の要求で `previous_response_id: null` を送ると 400 になる。値がないときは項目ごと送らない。
- **セッションは基盤が決める**: Foundry 上では、最初の応答で返る `agent_session_id` を次の要求から入れる (ローカルとは逆)。
- **URL がパーセント エンコードされる**: モデルが探索のツールの URL をエンコードした形で `propose_display` に渡した。照合では表記をそろえる必要がある。
- **終了の判定**: 承認の後に再開した応答には、元のツール呼び出しが含まれない。ツールの結果だけで判定する。
- **コンテンツフィルター**: 遮断されると英語の定型文と未完了の応答になる。ワークフローで検知して日本語の定型文と相談先を出す処理と、画面で未完了 (`response.incomplete`) を扱う処理が必要。
