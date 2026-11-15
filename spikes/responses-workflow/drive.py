"""Drive a consultation against a Responses endpoint, approving every proposal.

Usage: uv run python drive.py [base_url] [--token]
  --token adds an Entra ID bearer token (https://ai.azure.com/.default) for a deployed hosted agent.
"""

import json
import os
import sys
import uuid

from openai import OpenAI

MESSAGES = json.loads(os.environ.get("DRIVE_MESSAGES", "null")) or [
    "子どもの予防接種について知りたい",
    "今日の天気を教えて",
    "ありがとう、もう大丈夫です。終わりにします",
]
PROFILE = {"gender": "無回答", "age": "30代", "ward": "中央区"}
FEEDBACK = {"rating": 5, "comment": "わかりやすかった"}


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base_url = args[0] if args else "http://localhost:8088"
    headers = {}
    if "--token" in sys.argv:
        from azure.identity import DefaultAzureCredential

        headers["Authorization"] = f"Bearer {DefaultAzureCredential().get_token('https://ai.azure.com/.default').token}"
    query = {"api-version": "v1"} if "--token" in sys.argv else None
    client = OpenAI(base_url=base_url, api_key="unused", default_headers=headers, default_query=query)
    # Locally the caller picks the session; a deployed agent returns the platform session to reuse.
    session = None if "--token" in sys.argv else uuid.uuid4().hex
    previous = None
    messages = iter(MESSAGES)
    turn_input: object = "start"

    while True:
        extra = {"agent_session_id": session} if session else {}
        # The Foundry endpoint rejects explicit nulls, so omit previous_response_id on the first turn.
        chain = {"previous_response_id": previous} if previous else {}
        stream = client.responses.create(input=turn_input, stream=True, store=True, extra_body=extra, **chain)
        text, output = "", []
        for event in stream:
            if event.type == "response.output_text.delta":
                text += event.delta
            elif event.type == "response.output_item.done":
                item = event.item.model_dump()
                if item["type"] in ("function_call", "mcp_approval_request"):
                    print(f"  [{item['type']}] {item.get('name')} {item.get('arguments', '')[:160]}")
                elif item["type"] == "function_call_output":
                    print(f"  [function_call_output] {item.get('output', '')[:160]}")
            elif event.type in ("response.completed", "response.failed"):
                previous = event.response.id
                session = session or (event.response.model_extra or {}).get("agent_session_id")
                output = [o.model_dump() for o in event.response.output]
                if event.type == "response.failed":
                    print("  FAILED:", event.response.error)
                    return
        if text:
            print(f"  assistant: {text}")

        approval = next((o for o in output if o["type"] == "mcp_approval_request"), None)
        answered = {o["call_id"] for o in output if o["type"] == "function_call_output"}
        pending = next(
            (o for o in output if o["type"] == "function_call" and o["name"] == "request_info" and o["call_id"] not in answered),
            None,
        )
        if approval:
            print(f"> approve {approval['name']}")
            turn_input = [{"type": "mcp_approval_response", "approval_request_id": approval["id"], "approve": True}]
        elif pending:
            request = json.loads(pending["arguments"])["request"]
            if request["request_type"] == "form":
                value = PROFILE if request["metadata"]["form"] == "profile" else FEEDBACK
            else:
                value = {"text": next(messages, "終わりにします"), "currentUrl": "/"}
            print(f"> {request['request_type']}: {json.dumps(value, ensure_ascii=False)}")
            turn_input = [{"type": "function_call_output", "call_id": pending["call_id"], "output": json.dumps(value)}]
        else:
            print("completed")
            return


if __name__ == "__main__":
    main()
