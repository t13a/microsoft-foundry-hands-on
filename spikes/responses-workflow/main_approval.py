"""Spike: an AgentExecutor whose agent calls a plain tool and an approval-required tool.

A scripted stub model drives the tool calls, so no Azure resources are needed. Checks how
tool calls, tool results, and approval requests appear in the outer Responses stream.
"""

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorRequest,
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    Executor,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    tool,
)
from agent_framework_foundry_hosting import CheckpointStoreProvider, HostedResponseRequest, ResponsesHostServer, WorkflowTurn

SEARCH_URL = "/search?q=予防接種"


def search_services(query: str) -> dict:
    """Search services by keyword."""
    return {"url": f"/search?q={query}", "count": 3}


def propose_display(urls: list[str], summary: str) -> dict:
    """Ask the user before showing the given URLs."""
    return {"url": urls[0]}


class ScriptedChatClient(FunctionInvocationLayer, BaseChatClient):
    """Call search_services, then propose_display, then answer; decided by the last message."""

    def _next(self, messages):
        last = messages[-1]
        results = [c for c in last.contents if c.type == "function_result"]
        if not results:
            return [Content.from_text("お調べします。"),
                    Content.from_function_call("c1", "search_services", arguments={"query": "予防接種"})]
        if results[0].call_id == "c1":
            return [Content.from_function_call(
                "c2", "propose_display", arguments={"urls": [SEARCH_URL], "summary": "予防接種に関するサービス"})]
        return [Content.from_text("表示しました。ほかにお探しのものはありますか？")]

    def _inner_get_response(self, *, messages, stream, options, **kwargs):
        contents = self._next(messages)
        if stream:

            async def _stream():
                for content in contents:
                    yield ChatResponseUpdate(role="assistant", contents=[content])

            return ResponseStream(_stream(), finalizer=ChatResponse.from_updates)

        async def _response():
            return ChatResponse(messages=[Message(role="assistant", contents=contents)])

        return _response()


class Start(Executor):
    def __init__(self) -> None:
        super().__init__(id="start")

    @handler
    async def start(self, text: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        await ctx.send_message(AgentExecutorRequest(messages=[Message("user", text)], should_respond=True))


def build_workflow(request: HostedResponseRequest) -> Workflow:
    start = Start()
    # Tools are wrapped per request: hosted native workflows reject objects shared across requests.
    tools = [tool(search_services), tool(propose_display, approval_mode="always_require")]
    agent = Agent(client=ScriptedChatClient(), name="SearchAssistant", tools=tools)
    assistant = AgentExecutor(agent, id="assistant")
    return (
        WorkflowBuilder(name="approval-spike-v1", start_executor=start, output_from=[assistant])
        .add_edge(start, assistant)
        .build()
    )


async def parse_response(request: HostedResponseRequest) -> WorkflowTurn:
    items = await request.get_input_items()
    if any(item.get("type") in ("function_call_output", "mcp_approval_response") for item in items):
        return WorkflowTurn(responses=await request.get_workflow_responses())
    return WorkflowTurn(input=await request.get_input_text() or "")


if __name__ == "__main__":
    ResponsesHostServer(
        workflow=build_workflow, parse_response=parse_response, checkpoint_store_provider=CheckpointStoreProvider()
    ).run()
