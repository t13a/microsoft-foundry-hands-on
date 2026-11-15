"""Spike for V-3: create (a new version of) the search-assistant prompt agent in Foundry.

Usage: FOUNDRY_PROJECT_ENDPOINT=... uv run python create_prompt_agent.py [model-deployment]
"""

import os
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential

AGENT_NAME = "search-assistant"

INSTRUCTIONS = """\
あなたは出茂市の住民向けサービス検索サイトの検索アシスタントです。

担当業務:
- 利用者の要望を聞き、サイトのカテゴリや検索から該当する住民向けサービスを探して、表示を提案します。

守ること:
- 担当業務以外の会話には応じず、一般知識の情報提供もしません。丁寧に断り、サービス探しに誘導します。
- サービスの名称・説明・住所・電話番号・URL をチャットで答えてはいけません。必ず propose_display で画面に表示します。
- propose_display に渡す urls は、search_services などツールの結果に含まれる URL をそのまま使います。URL を作ったり書き換えたりしません。
- propose_display の summary は利用者の要望の言い換えにとどめ、サービスの具体的な情報を含めません。
- 必要に応じて suggest_replies で推奨の選択肢を示します。
- 利用者の用件が済んだら「ほかにお探しのものはありますか？」と尋ね、利用者が終了を望んだら propose_end を呼びます。
- 応答は短く、やさしい日本語で書きます。
"""


def tools() -> list[FunctionTool]:
    def fn(name: str, description: str, properties: dict, required: list[str]) -> FunctionTool:
        return FunctionTool(
            name=name,
            description=description,
            parameters={"type": "object", "properties": properties, "required": required, "additionalProperties": False},
            strict=True,
        )

    return [
        fn(
            "search_services",
            "キーワードで住民向けサービスを検索し、一致したサービスと表示用の URL を返す。",
            {"query": {"type": "string", "description": "検索語"}},
            ["query"],
        ),
        fn(
            "propose_display",
            "検索で見つかった内容を画面に表示してよいか、利用者に確認する。承認されたら表示する URL が返る。",
            {
                "urls": {"type": "array", "items": {"type": "string"}, "description": "ツールの結果に含まれる URL"},
                "summary": {"type": "string", "description": "利用者の要望の言い換え"},
            },
            ["urls", "summary"],
        ),
        fn(
            "suggest_replies",
            "利用者に推奨の選択肢を示す。",
            {"options": {"type": "array", "items": {"type": "string"}, "description": "選択肢の文言"}},
            ["options"],
        ),
        fn("propose_end", "相談を終了してよいか、利用者に確認する。", {}, []),
    ]


def main() -> None:
    model = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-5-mini")
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential) as project,
    ):
        agent = project.agents.create_version(
            agent_name=AGENT_NAME,
            definition=PromptAgentDefinition(model=model, instructions=INSTRUCTIONS, tools=tools()),
        )
        print(f"created {agent.name} version {agent.version} (model {model})")


if __name__ == "__main__":
    main()
