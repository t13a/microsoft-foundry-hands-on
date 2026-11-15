"""Spike for V-3: the V-10 flow with the Foundry prompt agent (search-assistant) as the consultation agent.

AGENT_MODE=foundry (default) uses the prompt agent by name without pinning a version;
AGENT_MODE=stub uses the scripted client from main_v10 (no Azure).
"""

import os

from agent_framework import Agent, AgentContext, AgentExecutor, Workflow, WorkflowBuilder, agent_middleware, tool
from agent_framework.foundry import FoundryAgent
from agent_framework_foundry_hosting import CheckpointStoreProvider, HostedResponseRequest, ResponsesHostServer
from azure.identity import DefaultAzureCredential

import main_v10
from main_v10 import Coordinator, InputRequest, ScriptedChatClient, parse_response, propose_display, propose_end, suggest_replies


def search_services(query: str) -> dict:
    """Search services by keyword (fixed sample data for the spike)."""
    path = "/c/子育て・教育/健診・予防接種/予防接種"
    return {
        "url": f"/search?q={query}",
        "count": 2,
        "services": [
            {"name": "予防接種相談窓口", "categoryPath": ["子育て・教育", "健診・予防接種", "予防接種"],
             "url": f"{path}#svc=予防接種相談窓口", "description": "予防接種の種類や時期の相談"},
            {"name": "任意予防接種費用助成", "categoryPath": ["子育て・教育", "健診・予防接種", "予防接種"],
             "url": f"{path}#svc=任意予防接種費用助成", "description": "任意接種の費用の一部を助成"},
        ],
    }


def build_tools():
    # Created per request: hosted native workflows reject objects shared across requests.
    return [
        tool(search_services),
        tool(propose_display, approval_mode="always_require"),
        tool(suggest_replies),
        tool(propose_end, approval_mode="always_require"),
    ]


def _drop_continuation_token(update):
    update.continuation_token = None
    return update


@agent_middleware
async def drop_continuation_tokens(context: AgentContext, call_next) -> None:
    """The OpenAI Responses client marks in-progress stream updates with a continuation token,
    which the native workflow host treats as unfinished background output and rejects."""
    if context.stream:
        context.stream_transform_hooks.append(_drop_continuation_token)
    await call_next()


def build_agent():
    if os.environ.get("AGENT_MODE", "foundry") == "stub":
        return Agent(client=ScriptedChatClient(), name="SearchAssistant", tools=build_tools())
    return FoundryAgent(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        agent_name="search-assistant",  # no version: use the latest one saved in Foundry
        credential=DefaultAzureCredential(),
        tools=build_tools(),
        # The workflow host keeps the history; the hosted workflow requires the agent not to store it.
        default_options={"store": False},
        middleware=[drop_continuation_tokens],
    )


def build_workflow(request: HostedResponseRequest) -> Workflow:
    coordinator = Coordinator()
    assistant = AgentExecutor(build_agent(), id="assistant")
    return (
        WorkflowBuilder(name="consultation-v3", start_executor=coordinator, output_from=[coordinator, assistant])
        .add_edge(coordinator, assistant)
        .add_edge(assistant, coordinator)
        .build()
    )


if __name__ == "__main__":
    main_v10.search_services = search_services
    ResponsesHostServer(
        workflow=build_workflow,
        parse_response=parse_response,
        checkpoint_store_provider=CheckpointStoreProvider(
            allowed_checkpoint_types=[f"{InputRequest.__module__}:{InputRequest.__qualname__}"],
        ),
    ).run()
