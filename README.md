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
CONSULTATION_MODE=stub AGENTSERVER_STATE_ROOT=.agentserver uv run python -m consultation
```

```bash
npm run build --prefix web/ui && uv run python -m web_api
```

http://localhost:8000 を開きます。BFF はビルドした SPA を配信し、`/api/responses` を localhost:8088 のホスト型エージェントへ中継します。SPA の開発サーバー (`npm run dev --prefix web/ui`) を使う場合、`/api` は localhost:8000 の BFF へ中継されます。

## Azure へのデプロイ

前提: [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/) (azd 1.37 以上、拡張 `azure.ai.agents`)、Azure CLI。`azd auth login` と `az login` を済ませておきます。web のイメージは GitHub Actions が GHCR に置きます (`main` への push で更新)。

```bash
azd env new dev --subscription <subscription-id> --location japaneast
```

```bash
azd env set AZURE_RESOURCE_GROUP rg-foundry-hands-on-dev && azd env set AZURE_FOUNDRY_RESOURCE_GROUP rg-foundry-hands-on-dev && azd env set AZURE_AI_PROJECT_NAME ai-project-demo-city
```

```bash
azd env set BASIC_AUTH_PASSWORD <password> && azd env set BUDGET_EMAIL <address>
```

初回は、レイヤーを順に流してから、エージェントをデプロイし、エージェントの ID にロールを付けるため `app` をもう一度流します。

```bash
azd provision foundry && azd provision app && azd hooks run postprovision
```

```bash
azd deploy consultation-workflow && azd provision app
```

サイトの URL は `azd env get-value WEB_URL`、ユーザー名は `demo`、パスワードは `azd env get-value BASIC_AUTH_PASSWORD` で確かめます。詳しくは [基本設計書](docs/design.md) の 9.4。
