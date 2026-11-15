# 相談のワークフロー (`consultation`)

Foundry のホスト型エージェントとして動く、相談のワークフロー (基本設計書 4 章、5 章)。

| パス | 内容 |
|---|---|
| `src/consultation/workflow.py` | グラフと進行役 (案内 → プロフィール → 相談ループ → 終了 → フィードバック → お礼) |
| `src/consultation/tools.py` | 相談役のツール (カタログを使う探索、表示提案の照らし合わせなど) |
| `src/consultation/stub.py` | 台本どおりに動くスタブのチャットクライアント |
| `src/consultation/server.py` | Responses のホスト (`python -m consultation`) |
| `src/consultation/drive.py` | 相談を CLI で最後まで動かす |
| `content/` | 案内とお礼の文言、やり取りの上限 (`messages.toml`)、フォームの JSON Schema |
| `prompt-agent/` | プロンプト エージェントの指示文とツール定義の初期版、なければ作るスクリプト |

## 起動 (localhost:8088)

スタブ (Azure なし):

```bash
AGENT_MODE=stub AGENTSERVER_STATE_ROOT=.agentserver uv run python -m consultation
```

Foundry のプロンプト エージェントを使う:

```bash
AGENT_MODE=foundry FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project> AGENTSERVER_STATE_ROOT=.agentserver uv run python -m consultation
```

| 環境変数 | 既定 | 内容 |
|---|---|---|
| `AGENT_MODE` | `foundry` | `stub` か `foundry` |
| `STUB_SCENARIO` | `default` | スタブの台本 (`default`、`category`、`multiple`、`search`、`fabricated`、`content_filter`、`content_filter_error`。中身は `stub.py` の冒頭) |
| `FOUNDRY_PROJECT_ENDPOINT` | — | Foundry プロジェクトのエンドポイント (`foundry` のとき) |
| `FOUNDRY_AGENT_NAME` | `search-assistant` | 呼び出すプロンプト エージェントの名前 (版は固定しない) |
| `CATALOG_DIR` | リポジトリの `data/` | カタログの CSV の場所 (BFF と同じ名前) |
| `CONSULTATION_CONTENT_DIR` | `agent/content` | 文言とフォームの場所 |
| `AGENTSERVER_STATE_ROOT` | `~/.agentserver` | ローカルのワークフローの状態の保存先 |
| `PORT` | `8088` | 待ち受けるポート |

## CLI で相談を動かす

```bash
uv run python -m consultation.drive
```

既定は「探す → 案内カード → `@open` (表示する) → 見つかった → ない → 終了の承認 → アンケート」。発言は引数で変えられる (`@open` は直前の案内カードを表示したことを表す)。`--interactive` で標準入力から、`--reject-end` で最初の終了の提案を却下、`--skip-feedback` でアンケートをスキップ、`--token` でデプロイしたホスト型エージェントに Entra ID のトークンを付けて送る。

## 画面とのやり取り

基本設計書 3.2 のとおり、Responses の標準の項目でやり取りする。

| 項目 | 形 |
|---|---|
| 入力待ち | `request_info` の `function_call`。引数の `request` は `{"request_type": "user_message" \| "form", "message": "…", "metadata": {…}}`。フォームの `metadata` は `{"form": "profile" \| "feedback", "schema": {JSON Schema}}`、フィードバックには `"skippable": true` が付く |
| 発言の返事 | `function_call_output` の `output` に `{"text": "…", "url": "/c/…"}`。案内カードから表示した後は `"event": "opened"` を添える (`text` は空でよい) |
| フォームの返事 | 入力値の JSON。フィードバックをスキップしたら `{"skipped": true}` |
| `propose_display` の結果 | 成功: `{"url": "<エンコード済みの URL>", "count": <件数>}`。失敗: `{"error": "表示できませんでした", "reason": "…"}` (カードを出さない) |
| `propose_end` | `mcp_approval_request` で承認を求める。承認後の結果は `{"ended": true}` |
| `suggest_replies` | 引数 `{"options": ["…"]}`。結果は `{"shown": true}` |
| `show_emergency_contacts` | 引数なし。結果は `{"shown": true}` |

件数は、強調表示があればその数、カテゴリだけならカテゴリ直下のサービスの数、検索なら一致した数。

## プロンプト エージェントを作る

```bash
FOUNDRY_PROJECT_ENDPOINT=... uv run python agent/prompt-agent/create.py [model-deployment]
```

同じ名前のエージェントがあれば何もしない (Foundry 側が正本)。`tools.json` とツールの実装が食い違わないことは `agent/tests/test_tools.py` で確かめている。
