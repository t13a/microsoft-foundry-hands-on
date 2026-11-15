"""Spike: host a declarative YAML workflow with ResponsesHostServer, using a stub chat client.

Checks V-1 (pauses as standard Responses items), V-4 (stub), V-8 (form metadata), and how
InvokeAzureAgent surfaces agent output (streaming or not).
"""

from pathlib import Path

from agent_framework import Agent, BaseChatClient, ChatResponse, ChatResponseUpdate, Message, ResponseStream, Workflow
from agent_framework.declarative import WorkflowFactory
from agent_framework_foundry_hosting import CheckpointStoreProvider, HostedResponseRequest, ResponsesHostServer, WorkflowTurn

WORKFLOW_PATH = Path(__file__).with_name("consultation.yaml")


class StubChatClient(BaseChatClient):
    """Return a fixed reply in three chunks so streaming is observable."""

    REPLY = ["小さなお子さんの", "予防接種について", "お調べしますね。"]

    def _inner_get_response(self, *, messages, stream, options, **kwargs):
        if stream:

            async def _stream():
                for chunk in self.REPLY:
                    yield ChatResponseUpdate(role="assistant", contents=[{"type": "text", "text": chunk}])

            return ResponseStream(_stream(), finalizer=ChatResponse.from_updates)

        async def _response():
            return ChatResponse(messages=[Message(role="assistant", contents=["".join(self.REPLY)])])

        return _response()


def declarative_checkpoint_types() -> list[str]:
    """Allow the declarative package's own message and request types in checkpoints."""
    import importlib
    import inspect
    import pkgutil

    import agent_framework_declarative._workflows as pkg

    names: list[str] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        module = importlib.import_module(f"{pkg.__name__}.{info.name}")
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ == module.__name__:
                names.append(f"{cls.__module__}:{cls.__qualname__}")
    return names


def build_workflow(request: HostedResponseRequest) -> Workflow:
    agent = Agent(client=StubChatClient(), name="SearchAssistant", instructions="stub")
    factory = WorkflowFactory().register_agent("SearchAssistant", agent)
    return factory.create_workflow_from_yaml_path(WORKFLOW_PATH)


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
            allowed_checkpoint_types=declarative_checkpoint_types(),
        ),
    ).run()
