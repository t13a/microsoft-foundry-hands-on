"""プロンプト エージェント (search-assistant) がなければ作る。あれば何もしない。

初回のデプロイで作り、それ以降は Foundry 側を正本とする (基本設計書 5.1)。既存のエージェントは
上書きしない。指示文とツール定義を変えたら、Foundry ポータルで新しい版を保存する。

使い方:
    FOUNDRY_PROJECT_ENDPOINT=... uv run python agent/prompt-agent/create.py [model] [--update]

`--update` を付けると、リポジトリの指示文とツール定義で新しい版を保存する (Foundry ポータルでの
変更は上書きされるので、明示したときだけ)。推論の努力は SEARCH_AGENT_REASONING (既定 low)。

エージェント名は SEARCH_AGENT_NAME (既定 search-assistant)、モデルは引数か
AZURE_AI_MODEL_DEPLOYMENT_NAME (既定 gpt-5-mini)。要: Foundry User ロール。
"""

import json
import os
import sys
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition, Reasoning
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential

HERE = Path(__file__).resolve().parent
DEFAULT_AGENT_NAME = "search-assistant"
DEFAULT_MODEL = "gpt-5-mini"


def definition(model: str) -> PromptAgentDefinition:
    instructions = (HERE / "instructions.md").read_text(encoding="utf-8")
    tools = json.loads((HERE / "tools.json").read_text(encoding="utf-8"))
    return PromptAgentDefinition(
        model=model,
        instructions=instructions,
        tools=[FunctionTool(**t, strict=True) for t in tools],
        # gpt-5 family models reason before answering; a low effort keeps each turn short.
        reasoning=Reasoning(effort=os.environ.get("SEARCH_AGENT_REASONING", "low")),
    )


def main() -> None:
    name = os.environ.get("SEARCH_AGENT_NAME", DEFAULT_AGENT_NAME)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    update = "--update" in sys.argv[1:]
    model = args[0] if args else None
    model = model or os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", DEFAULT_MODEL)
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(
            endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential
        ) as project,
    ):
        try:
            project.agents.get(name)
            if update:
                raise ResourceNotFoundError("update requested")
        except ResourceNotFoundError:
            agent = project.agents.create_version(agent_name=name, definition=definition(model))
            print(f"created {agent.name} version {agent.version} (model {model})")
            return
        print(f"{name} already exists; nothing to do")


if __name__ == "__main__":
    main()
