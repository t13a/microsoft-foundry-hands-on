# 技術検証 V-10: 画面とストリームの接続 (ローカル、スタブ)

2026-11-15 実施。`spikes/responses-workflow/main_v10.py` (相談の流れ全体を台本どおりのスタブで動かすワークフロー) に、OpenAI の JavaScript SDK と assistant-ui でつないだ。Azure には接続していない。

## 使ったパッケージ

| パッケージ | 版 |
|---|---|
| @assistant-ui/react | 0.15.36 |
| openai | 7.57.0 |
| react | 19.3.1 |
| vite | 8.3.8 |

## ファイル

| ファイル | 内容 |
|---|---|
| `scripts/check-stream.mjs` | OpenAI の SDK だけで相談の最初から最後までを通すスクリプト |
| `src/consultation.ts` | Responses のストリームを会話の状態に変換するアダプター (設計書 3.2 の対応表の実装) |
| `src/Chat.tsx` | assistant-ui の外部ストア用ランタイムとプリミティブで作ったチャット領域。フォーム、承認、推奨の選択肢、遷移ボタン |
| `src/index.css` | 要求仕様書 5.3 のデザイントークンを CSS 変数にした見た目 |

## 動かし方

```bash
# 1. スタブのワークフロー (localhost:8088)
cd spikes/responses-workflow
AGENTSERVER_STATE_ROOT=$PWD/.agentserver uv run python main_v10.py

# 2a. SDK だけで確認
cd spikes/chat-ui
node scripts/check-stream.mjs

# 2b. 画面で確認 (/api は BFF の代わりに 8088 へ中継する)
npm run build && npm run preview
```

## 結果: ○

- OpenAI の SDK で、独自の項目 (`mcp_approval_request`、名前が `request_info` の `function_call`) を含むストリームを、そのまま型付きのイベントとして受け取れた。Foundry 独自の `agent_session_id` は、要求の本文にそのまま入れて送れた。
- 画面で、案内 → プロフィールのフォーム → 発言 → 検索 → 表示提案の確認 → 承認 → コンテンツ領域の遷移 → 推奨の選択肢 → 終了の確認 → アンケート → 完了、まで通った。文章は少しずつ表示された。
- 承認待ちや処理中は、入力欄の送信を止められた (`isSendDisabled`)。
- デザイントークンは、プリミティブに自分の CSS を当てるだけで反映できた (Tailwind は不要)。

## 分かったこと

- **承認の要求とツールの呼び出しは ID で結ばれていない**: `mcp_approval_request` には、どの `function_call` への承認かを示す ID がない。同じ名前で、まだ承認の要求と結びついていない直近の呼び出しに対応づけた。同じツールを並べて呼ぶ場合は、引数も比べる必要がある。
- **結果は次の応答で届くことがある**: `propose_display` の結果 (`function_call_output`) は、承認を送った次の応答で届く。アダプターは、過去のメッセージも含めてツールの呼び出しを探す必要がある。
- **ツール UI の登録方法**: `makeAssistantToolUI` は非推奨になっていた。メッセージの各部分を `MessagePrimitive.Parts` の子として描画する方式にした。
- **バンドルの大きさ**: 約 986 kB (gzip で約 263 kB)。チャット領域は CTA で呼び出すので、チャット領域だけを遅延読み込みにすれば、サイトの初回表示には影響しない。
- **開発サーバー**: アプリの内蔵ブラウザーでは Vite の開発用スクリプト (`/@vite/client`) が遮断されて画面が出なかったため、確認はビルドして `vite preview` で行った。手元のブラウザーなら開発サーバーで動く見込み。
- 日本語入力 (IME の確定の Enter で送信されないか) とスクリーンリーダーの動作は、自動操作では確認できていない。
