"""Spike: the same flow as consultation.yaml, built in code with an AgentExecutor.

Checks whether agent text streams as Responses deltas when the workflow is code-defined.
"""

from dataclasses import dataclass, field
from typing import Any

from agent_framework import (
    Agent,
    AgentExecutor,
    AgentExecutorRequest,
    Executor,
    Message,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)
from agent_framework_foundry_hosting import CheckpointStoreProvider, HostedResponseRequest, ResponsesHostServer, WorkflowTurn

from main_declarative import StubChatClient


@dataclass
class InputRequest:
    """A pause the UI renders by request_type: a form (with its schema) or the user's next message."""

    request_type: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "gender": {"enum": ["男性", "女性", "その他", "無回答"]},
        "age": {"enum": ["10歳未満", "10代", "20代", "30代", "40代", "50代", "60代", "70代", "80歳以上", "無回答"]},
        "ward": {"enum": ["中央区", "北区", "南区", "市外", "無回答"]},
    },
    "required": ["gender", "age", "ward"],
}


class Intake(Executor):
    def __init__(self) -> None:
        super().__init__(id="intake")

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest, str]) -> None:
        await ctx.yield_output("ご利用ありがとうございます。生成 AI を使って窓口をご案内します。")
        await ctx.request_info(
            InputRequest("form", "プロフィールを入力してください。", {"schema": PROFILE_SCHEMA}), dict
        )

    @response_handler
    async def on_input(
        self, request: InputRequest, response: dict, ctx: WorkflowContext[AgentExecutorRequest, str]
    ) -> None:
        if request.request_type == "form":
            ctx.set_state("profile", response)
            await ctx.request_info(InputRequest("user_message", "ご用件をどうぞ。"), dict)
            return
        profile = ctx.get_state("profile")
        await ctx.send_message(
            AgentExecutorRequest(
                messages=[Message("user", f"プロフィール: {profile}\n相談: {response['text']}")], should_respond=True
            )
        )


def build_workflow(request: HostedResponseRequest) -> Workflow:
    intake = Intake()
    assistant = AgentExecutor(
        Agent(client=StubChatClient(), name="SearchAssistant", instructions="stub"), id="assistant"
    )
    return (
        WorkflowBuilder(name="consultation-code-v1", start_executor=intake, output_from=[intake, assistant])
        .add_edge(intake, assistant)
        .build()
    )


async def parse_response(request: HostedResponseRequest) -> WorkflowTurn:
    items = await request.get_input_items()
    if any(item.get("type") in ("function_call_output", "mcp_approval_response") for item in items):
        return WorkflowTurn(responses=await request.get_workflow_responses())
    return WorkflowTurn(input=await request.get_input_text() or "")


if __name__ == "__main__":
    ResponsesHostServer(
        workflow=build_workflow,
        parse_response=parse_response,
        checkpoint_store_provider=CheckpointStoreProvider(
            allowed_checkpoint_types=[f"{InputRequest.__module__}:{InputRequest.__qualname__}"],
        ),
    ).run()
