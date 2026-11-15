# 出茂市 くらしのサービス案内 (Microsoft Foundry の PoC)

架空の市「出茂市 (でもし)」の住民向けサービス検索サイトと、AI 検索アシスタントの PoC です。

- [要求仕様書](docs/requirements.md)
- [基本設計書](docs/design.md)
- [実装計画](docs/implementation-plan.md)

## 構成

| パス | 内容 |
|---|---|
| `packages/catalog` | CSV の読み込み・検証・検索・URL (BFF とホスト型エージェントで共有) |
| `agent` | 相談のワークフロー (Foundry のホスト型エージェント) |
| `web/api` | BFF (FastAPI) |
| `web/ui` | SPA (React + TypeScript) |
| `data` | 架空データの CSV |
| `spikes` | 技術検証のコード (本実装の参考) |

## ローカル開発

前提: [uv](https://docs.astral.sh/uv/)、Node.js 22 以上。

```bash
uv sync
```

```bash
uv run pytest
```

```bash
uv run ruff check && uv run ruff format --check
```

```bash
npm install --prefix web/ui
```

```bash
npm test --prefix web/ui
```

画面から相談を試すとき (Azure なし、スタブのモデル):

```bash
AGENT_MODE=stub AGENTSERVER_STATE_ROOT=.agentserver uv run python -m consultation
```

```bash
npm run build --prefix web/ui && uv run python -m web_api
```

http://localhost:8000 を開きます。BFF はビルドした SPA を配信し、`/api/responses` を localhost:8088 のホスト型エージェントへ中継します。SPA の開発サーバー (`npm run dev --prefix web/ui`) を使う場合、`/api` は localhost:8000 の BFF へ中継されます。
