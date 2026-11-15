"""相談のワークフロー: 進行役 (Coordinator) と相談役 (AgentExecutor) のグラフ (基本設計書 4 章)。

進行役の流れ: 案内 → プロフィールのフォーム → 発言の待ち受け → 相談役 → (終了の判定) →
フィードバックのフォーム → お礼。入力待ちは `request_info` で、画面には名前が `request_info` の
`function_call` として届く (基本設計書 3.2)。
"""

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

from agent_framework import (
    Agent,
    AgentContext,
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    Executor,
    Message,
    ResponseStream,
    SupportsAgentRun,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    agent_middleware,
    handler,
    response_handler,
)
from agent_framework.exceptions import ChatClientContentFilterException
from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    HostedResponseRequest,
    WorkflowTurn,
)
from opentelemetry import trace

from consultation import content as content_data
from consultation import tools as tool_impl

logger = logging.getLogger(__name__)

AGENT_MODE_ENV = "CONSULTATION_MODE"
PROJECT_ENDPOINT_ENV = "FOUNDRY_PROJECT_ENDPOINT"
AGENT_NAME_ENV = "SEARCH_AGENT_NAME"
DEFAULT_AGENT_NAME = "search-assistant"

# 相談役への発言に添える文脈の見出し。スタブの台本もこの見出しで読み取る。
PROFILE_LABEL = "[利用者のプロフィール]"
URL_LABEL = "[利用者が今見ている画面]"
EVENT_LABEL = "[出来事]"
TEXT_LABEL = "[利用者の発言]"
OPENED_NOTE = "利用者が案内カードの「表示する」を押して、画面を表示しました。"


@dataclass
class InputRequest:
    """画面への入力待ち。画面は `request_type` で描き分ける (発言の入力欄、またはフォーム)。"""

    request_type: str
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


def compose_message(profile: dict[str, Any], schema: dict[str, Any], reply: dict[str, Any]) -> str:
    """利用者の発言に、プロフィール、今見ている画面、出来事を添える (基本設計書 4.1)。

    URL はモデルが読めるようにデコードして添える (ツールの照らし合わせは表記の違いを吸収する)。
    """
    properties = schema.get("properties", {})
    # チェックポイントを経ると項目の順が変わるので、フォームの順に並べる。
    keys = [k for k in properties if k in profile] + [k for k in profile if k not in properties]
    items = (f"{properties.get(k, {}).get('title', k)}: {profile[k]}" for k in keys)
    lines = [PROFILE_LABEL + " " + "、".join(items)]
    if url := reply.get("url"):
        lines.append(f"{URL_LABEL} {unquote(str(url))}")
    if reply.get("event") == "opened":
        lines.append(f"{EVENT_LABEL} {OPENED_NOTE}")
    lines.append(f"{TEXT_LABEL} {reply.get('text') or ''}")
    return "\n".join(lines)


def record(name: str, session_id: str, **attributes: Any) -> None:
    """相談のイベントを記録する (基本設計書 8.2)。トレースのスパンのイベントとログに出す。"""
    attributes = {k: v for k, v in attributes.items() if v is not None}
    span_attributes = {
        "microsoft.session.id": session_id,
        **{
            k: v if isinstance(v, str | bool | int | float) else str(v)
            for k, v in attributes.items()
        },
    }
    trace.get_current_span().add_event(name, span_attributes)
    logger.info("%s session=%s %s", name, session_id, attributes)


def _function_results(response: AgentExecutorResponse) -> list[tuple[str | None, Any]]:
    """相談役の応答に含まれるツールの結果 (関数名がわかれば関数名つき)。"""
    contents = [c for m in response.agent_response.messages for c in m.contents]
    names = {c.call_id: c.name for c in contents if c.type == "function_call"}
    return [(names.get(c.call_id), c.result) for c in contents if c.type == "function_result"]


class Coordinator(Executor):
    """定型部と流れの判断を受け持つ進行役。状態はワークフローの状態 (チェックポイント) に置く。"""

    def __init__(self, content: content_data.Content, session_id: str) -> None:
        super().__init__(id="coordinator")
        self._content = content
        self._session_id = session_id

    @handler
    async def start(self, _: str, ctx: WorkflowContext[AgentExecutorRequest, str]) -> None:
        ctx.set_state("turns", 0)
        record("consultation.started", self._session_id)
        await ctx.yield_output(self._content.greeting)
        await self._request_form(ctx, "profile")

    @response_handler
    async def on_input(
        self,
        request: InputRequest,
        response: dict,
        ctx: WorkflowContext[AgentExecutorRequest, str],
    ) -> None:
        form = request.metadata.get("form")
        if form == "profile":
            ctx.set_state("profile", response)
            record("consultation.profile", self._session_id, **_prefixed("profile", response))
            await self._request_message(ctx, self._content.first_message)
        elif form == "feedback":
            record("consultation.feedback", self._session_id, **_prefixed("feedback", response))
            await ctx.yield_output(self._content.thanks)
        elif request.request_type == "user_message":
            turns = ctx.get_state("turns") + 1
            ctx.set_state("turns", turns)
            if response.get("event") == "opened":
                record("consultation.display_opened", self._session_id, url=response.get("url"))
            text = compose_message(ctx.get_state("profile"), self._content.profile_schema, response)
            await ctx.send_message(
                AgentExecutorRequest(messages=[Message("user", text)], should_respond=True)
            )

    @handler
    async def on_agent(
        self, response: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest, str]
    ) -> None:
        turns = ctx.get_state("turns")
        ended = False
        for name, result in _function_results(response):
            if (shown := tool_impl.display_result(result)) is not None:
                record("consultation.display_proposed", self._session_id, **shown)
            elif name in (None, "propose_end") and tool_impl.ended(result):
                ended = True
        if response.agent_response.finish_reason == "content_filter":
            record("consultation.content_filtered", self._session_id, turns=turns)
            await ctx.yield_output(self._content.content_filtered)
        if ended or turns >= self._content.max_turns:
            if not ended:
                await ctx.yield_output(self._content.turn_limit)
            reason = "propose_end" if ended else "turn_limit"
            record("consultation.ended", self._session_id, reason=reason, turns=turns)
            await self._request_form(ctx, "feedback")
        else:
            await self._request_message(ctx, "")

    async def _request_form(self, ctx: WorkflowContext, form: str) -> None:
        if form == "profile":
            message, schema, extra = self._content.profile_form, self._content.profile_schema, {}
        else:
            # フィードバックは送らずにスキップしてもよい (F-END-04)。
            message, schema = self._content.feedback_form, self._content.feedback_schema
            extra = {"skippable": True}
        await ctx.request_info(
            InputRequest("form", message, {"form": form, "schema": schema, **extra}), dict
        )

    async def _request_message(self, ctx: WorkflowContext, message: str) -> None:
        await ctx.request_info(InputRequest("user_message", message), dict)


def _prefixed(prefix: str, values: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}.{k}": v for k, v in values.items()}


@agent_middleware
async def handle_content_filter(context: AgentContext, call_next: Callable[[], Awaitable[None]]):
    """要求がコンテンツフィルターで弾かれた (例外になった) 場合も、終了理由 content_filter の
    応答に読み替える。応答の途中で遮断された場合は、クライアントが終了理由に入れて返す。"""
    try:
        await call_next()
    except ChatClientContentFilterException:
        logger.warning("The request was blocked by the content filter")
        context.result = AgentResponse(messages=[], finish_reason="content_filter")
        return
    if not context.stream or not isinstance(context.result, ResponseStream):
        return
    inner = context.result
    blocked = False

    async def guarded():
        nonlocal blocked
        try:
            async for update in inner:
                yield update
        except ChatClientContentFilterException:
            logger.warning("The response was blocked by the content filter")
            blocked = True

    async def finalize(updates):
        if blocked:
            response = AgentResponse.from_updates(updates)
            response.finish_reason = "content_filter"
            return response
        return await inner.get_final_response()

    context.result = ResponseStream(guarded(), finalizer=finalize)


def _drop_continuation_token(update):
    update.continuation_token = None
    return update


@agent_middleware
async def drop_continuation_tokens(
    context: AgentContext, call_next: Callable[[], Awaitable[None]]
) -> None:
    """OpenAI の Responses クライアントがストリーミング中の更新に付ける continuation token を外す。

    ワークフローのホストは、これを未完了の応答とみなして拒否する (プレリリース版の組み合わせの
    回避策。版を上げたら不要になるか確認する)。
    """
    if context.stream:
        context.stream_transform_hooks.append(_drop_continuation_token)
    await call_next()


def build_agent(tools: list, mode: str | None = None) -> SupportsAgentRun:
    """相談役のエージェントを作る。`CONSULTATION_MODE=stub` ならスタブ、`foundry` (既定) なら
    Foundry のプロンプト エージェントを名前で (版を固定せずに) 呼ぶ。"""
    mode = mode or os.environ.get(AGENT_MODE_ENV, "foundry")
    if mode == "stub":
        from consultation.stub import ScriptedChatClient

        return Agent(
            client=ScriptedChatClient(),
            name="search-assistant",
            tools=tools,
            middleware=[handle_content_filter],
        )
    if mode != "foundry":
        raise ValueError(f"{AGENT_MODE_ENV} must be 'stub' or 'foundry': {mode}")
    from agent_framework.foundry import FoundryAgent
    from azure.identity import DefaultAzureCredential

    return FoundryAgent(
        project_endpoint=os.environ[PROJECT_ENDPOINT_ENV],
        agent_name=os.environ.get(AGENT_NAME_ENV, DEFAULT_AGENT_NAME),
        # Empty, not None: on Foundry the platform injects FOUNDRY_AGENT_VERSION (the hosted
        # agent's own version), which would otherwise pin the prompt agent to that version.
        agent_version="",
        credential=DefaultAzureCredential(),
        tools=tools,
        # 会話の履歴はワークフローのホストが持つので、エージェント側には保存しない。
        default_options={"store": False},
        middleware=[handle_content_filter, drop_continuation_tokens],
    )


def build_workflow(request: HostedResponseRequest, *, mode: str | None = None) -> Workflow:
    """ワークフローを作る。ホストは要求ごとに呼び、部品やツールを使い回さない。"""
    coordinator = Coordinator(content_data.load(), request.scope.session_id)
    agent = build_agent(tool_impl.build_tools(tool_impl.load_catalog()), mode)
    assistant = AgentExecutor(agent, id="assistant")
    return (
        WorkflowBuilder(
            name="consultation",
            start_executor=coordinator,
            output_from=[coordinator, assistant],
        )
        .add_edge(coordinator, assistant)
        .add_edge(assistant, coordinator)
        .build()
    )


async def parse_response(request: HostedResponseRequest) -> WorkflowTurn:
    """返事 (`function_call_output`、`mcp_approval_response`) を含む要求なら待ち受けへの返事、
    それ以外なら相談の開始として扱う。"""
    items = await request.get_input_items()
    if any(item.get("type") in ("function_call_output", "mcp_approval_response") for item in items):
        return WorkflowTurn(responses=await request.get_workflow_responses())
    return WorkflowTurn(input=await request.get_input_text() or "start")


def checkpoint_store_provider() -> CheckpointStoreProvider:
    # チェックポイントに入る独自の型は、許可する型の一覧に登録する。
    return CheckpointStoreProvider(
        allowed_checkpoint_types=[f"{InputRequest.__module__}:{InputRequest.__qualname__}"],
    )
