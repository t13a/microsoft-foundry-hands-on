"""Spike for V-10: the full consultation flow with a scripted stub model.

Coordinator: greeting -> profile form -> user message -> agent -> (repeat) -> feedback form -> thanks.
Agent tools: search_services, propose_display (approval), suggest_replies, propose_end (approval).
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
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
    response_handler,
    tool,
)
from agent_framework_foundry_hosting import CheckpointStoreProvider, HostedResponseRequest, ResponsesHostServer, WorkflowTurn

MAX_TURNS = 30

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "gender": {"title": "性別", "enum": ["男性", "女性", "その他", "無回答"]},
        "age": {
            "title": "年代",
            "enum": ["10歳未満", "10代", "20代", "30代", "40代", "50代", "60代", "70代", "80歳以上", "無回答"],
        },
        "ward": {"title": "お住まいの区", "enum": ["中央区", "北区", "東区", "南区", "西区", "市外", "無回答"]},
    },
    "required": ["gender", "age", "ward"],
}

FEEDBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "rating": {"title": "満足度", "type": "integer", "minimum": 1, "maximum": 5},
        "comment": {"title": "ご意見 (任意)", "type": "string"},
    },
    "required": ["rating"],
}


@dataclass
class InputRequest:
    """A pause the UI renders by request_type: a form (with its schema) or the user's next message."""

    request_type: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


# Tool implementations. They are wrapped with tool() per request in build_workflow().
def search_services(query: str) -> dict:
    """Search services by keyword."""
    return {"url": f"/search?q={query}", "count": 3}


def propose_display(urls: list[str], summary: str) -> dict:
    """Ask the user before showing the given URLs."""
    return {"url": urls[0]}


def suggest_replies(options: list[str]) -> dict:
    """Show suggested replies to the user."""
    return {"shown": True}


def propose_end() -> dict:
    """Ask the user whether to end the consultation."""
    return {"ended": True}


class ScriptedChatClient(FunctionInvocationLayer, BaseChatClient):
    """Decide the next step from the last message, like a tiny model with a fixed script."""

    def _next(self, messages: list[Message]) -> list[Content]:
        last = messages[-1]
        results = [c for c in last.contents if c.type == "function_result"]
        if not results:
            if "終" in (last.text or ""):
                return [Content.from_function_call(f"end-{uuid.uuid4().hex[:8]}", "propose_end", arguments={})]
            return [
                Content.from_text("小さなお子さんの予防接種ですね。お調べします。"),
                Content.from_function_call(
                    f"search-{uuid.uuid4().hex[:8]}", "search_services", arguments={"query": "予防接種"}
                ),
            ]
        call_id = results[0].call_id or ""
        if call_id.startswith("search-"):
            return [
                Content.from_function_call(
                    f"display-{uuid.uuid4().hex[:8]}",
                    "propose_display",
                    arguments={"urls": ["/search?q=予防接種"], "summary": "小さなお子さんの予防接種に関するサービス"},
                )
            ]
        if call_id.startswith("display-"):
            if "url" not in str(results[0].result):
                return [Content.from_text("承知しました。ほかの条件でお探ししますか？")]
            return [
                Content.from_function_call(
                    f"suggest-{uuid.uuid4().hex[:8]}",
                    "suggest_replies",
                    arguments={"options": ["定期接種について", "費用の助成について", "相談を終わる"]},
                )
            ]
        if call_id.startswith("suggest-"):
            return [Content.from_text("表示しました。ほかにお探しのものはありますか？")]
        if call_id.startswith("end-"):
            return [Content.from_text("ご相談ありがとうございました。")]
        return [Content.from_text("（台本にない状態です）")]

    def _inner_get_response(self, *, messages, stream, options, **kwargs):
        contents = self._next(list(messages))
        if stream:

            async def _stream():
                for content in contents:
                    if content.type == "text":
                        # Split text so streaming is visible in the UI.
                        for chunk in (content.text[i : i + 6] for i in range(0, len(content.text), 6)):
                            yield ChatResponseUpdate(role="assistant", contents=[Content.from_text(chunk)])
                    else:
                        yield ChatResponseUpdate(role="assistant", contents=[content])

            return ResponseStream(_stream(), finalizer=ChatResponse.from_updates)

        async def _response():
            return ChatResponse(messages=[Message(role="assistant", contents=contents)])

        return _response()


def _ended(response: AgentExecutorResponse) -> bool:
    """True when this agent turn includes propose_end's approved result.

    After an approval the agent resumes, and the resumed response holds the function result
    but not the original function call, so match the result itself (only propose_end returns "ended").
    """
    contents = [c for m in response.agent_response.messages for c in m.contents]
    return any(c.type == "function_result" and "ended" in str(c.result) for c in contents)


class Coordinator(Executor):
    def __init__(self) -> None:
        super().__init__(id="coordinator")

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest, str]) -> None:
        ctx.set_state("turns", 0)
        await ctx.yield_output("ご利用ありがとうございます。生成 AI を使って、お探しのサービスをご案内します。")
        await ctx.request_info(
            InputRequest("form", "プロフィールを入力してください。", {"form": "profile", "schema": PROFILE_SCHEMA}),
            dict,
        )

    @response_handler
    async def on_input(
        self, request: InputRequest, response: dict, ctx: WorkflowContext[AgentExecutorRequest, str]
    ) -> None:
        if request.metadata.get("form") == "profile":
            ctx.set_state("profile", response)
            await ctx.request_info(InputRequest("user_message", "ご用件をどうぞ。"), dict)
        elif request.request_type == "user_message":
            ctx.set_state("turns", ctx.get_state("turns") + 1)
            context = f"[プロフィール] {ctx.get_state('profile')}\n[現在の URL] {response.get('currentUrl', '/')}"
            await ctx.send_message(
                AgentExecutorRequest(messages=[Message("user", f"{context}\n{response['text']}")], should_respond=True)
            )
        elif request.metadata.get("form") == "feedback":
            await ctx.yield_output("ご協力ありがとうございました。")

    @handler
    async def on_agent(self, response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest, str]) -> None:
        if _ended(response) or ctx.get_state("turns") >= MAX_TURNS:
            await ctx.request_info(
                InputRequest(
                    "form", "よろしければアンケートにご協力ください。", {"form": "feedback", "schema": FEEDBACK_SCHEMA}
                ),
                dict,
            )
        else:
            await ctx.request_info(InputRequest("user_message", ""), dict)


def build_workflow(request: HostedResponseRequest) -> Workflow:
    coordinator = Coordinator()
    tools = [
        tool(search_services),
        tool(propose_display, approval_mode="always_require"),
        tool(suggest_replies),
        tool(propose_end, approval_mode="always_require"),
    ]
    agent = Agent(client=ScriptedChatClient(), name="SearchAssistant", tools=tools)
    assistant = AgentExecutor(agent, id="assistant")
    return (
        WorkflowBuilder(name="consultation-v10", start_executor=coordinator, output_from=[coordinator, assistant])
        .add_edge(coordinator, assistant)
        .add_edge(assistant, coordinator)
        .build()
    )


async def parse_response(request: HostedResponseRequest) -> WorkflowTurn:
    items = await request.get_input_items()
    if any(item.get("type") in ("function_call_output", "mcp_approval_response") for item in items):
        return WorkflowTurn(responses=await request.get_workflow_responses())
    return WorkflowTurn(input=await request.get_input_text() or "start")


if __name__ == "__main__":
    ResponsesHostServer(
        workflow=build_workflow,
        parse_response=parse_response,
        checkpoint_store_provider=CheckpointStoreProvider(
            allowed_checkpoint_types=[f"{InputRequest.__module__}:{InputRequest.__qualname__}"],
        ),
    ).run()
