"""相談を CLI で最後まで動かす (技術検証の `drive.py` の後継)。

使い方:
    uv run python -m consultation.drive [base_url] [--token] [--reject-end] [--skip-feedback]
        [--interactive] [step ...]

step は発言の並び。`@open` は直前の案内カードの「表示する」を押したことを表す (本文が空の返事に
`event: "opened"` を添えて送る)。省略すると「探す → 案内カード → 表示 → 見つかった → ない」の流れ。
`--interactive` では標準入力から発言を読む (`@open` も使える)。
`--token` はデプロイしたホスト型エージェント向けに Entra ID のトークンを付ける。
"""

import argparse
import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

OPEN = "@open"
DEFAULT_STEPS = ["子どもの予防接種について知りたい", OPEN, "見つかった", "ない"]
PROFILE = {"gender": "無回答", "age": "30代", "ward": "中央区"}
FEEDBACK = {"rating": 5, "comment": "わかりやすかった"}


@dataclass
class Turn:
    """1 回の応答で起きたこと。"""

    text: str = ""
    status: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)

    def calls(self, name: str) -> list[dict[str, Any]]:
        return [i for i in self.items if i["type"] == "function_call" and i["name"] == name]

    def outputs(self, name: str) -> list[Any]:
        """サーバー側で実行済みのツールの結果 (同じ call_id の function_call_output)。"""
        ids = {i["call_id"] for i in self.calls(name)}
        return [
            json.loads(i["output"])
            for i in self.items
            if i["type"] == "function_call_output" and i["call_id"] in ids
        ]


@dataclass
class Driver:
    """利用者の代わりに、待ち受けに返事をしながら相談を進める。"""

    client: OpenAI
    hosted: bool = False
    approve_end: bool = True
    skip_feedback: bool = False
    log: Callable[[str], None] = print
    current_url: str = "/"
    session: str | None = None
    previous: str | None = None
    turns: list[Turn] = field(default_factory=list)
    _card: str | None = None

    def run(self, steps: Iterator[str]) -> list[Turn]:
        """相談の開始から、待ち受けのないまま応答が完了するまで進める。"""
        # ローカルでは呼び出し側がセッションを決める。Foundry 上では基盤が返すものを使う。
        self.session = None if self.hosted else uuid.uuid4().hex
        turn_input: Any = "start"
        while turn_input is not None:
            turn = self._send(turn_input)
            self.turns.append(turn)
            turn_input = self._reply(turn, steps)
        self.log("completed")
        return self.turns

    def _send(self, turn_input: Any) -> Turn:
        extra = {"agent_session_id": self.session} if self.session else {}
        # Foundry のエンドポイントは null を受け付けないので、最初は項目ごと省く。
        chain = {"previous_response_id": self.previous} if self.previous else {}
        stream = self.client.responses.create(
            input=turn_input, stream=True, store=True, extra_body=extra, **chain
        )
        turn = Turn()
        for event in stream:
            if event.type == "response.output_text.delta":
                turn.text += event.delta
            elif event.type == "response.output_item.done":
                item = event.item.model_dump()
                if item["type"] in ("function_call", "mcp_approval_request"):
                    self.log(f"  [{item['type']}] {item.get('name')} {item.get('arguments', '')}")
                elif item["type"] == "function_call_output":
                    self.log(f"  [function_call_output] {item.get('output', '')}")
            elif event.type in ("response.completed", "response.incomplete", "response.failed"):
                self.previous = event.response.id
                extra = event.response.model_extra or {}
                self.session = self.session or extra.get("agent_session_id")
                turn.status = event.response.status or event.type
                turn.items = [o.model_dump() for o in event.response.output]
                if event.type == "response.failed":
                    raise RuntimeError(f"response failed: {event.response.error}")
        if turn.text:
            self.log(f"  assistant: {turn.text}")
        if turn.status != "completed":
            self.log(f"  [{turn.status}]")
        for output in turn.outputs("propose_display"):
            if "url" in output:
                self._card = output["url"]
                self.log(f"  [card] {output['url']} ({output['count']})")
        return turn

    def _reply(self, turn: Turn, steps: Iterator[str]) -> Any:
        items = turn.items
        approval = next((o for o in items if o["type"] == "mcp_approval_request"), None)
        answered = {o["call_id"] for o in items if o["type"] == "function_call_output"}
        pending = next(
            (o for o in turn.calls("request_info") if o["call_id"] not in answered),
            None,
        )
        if approval:
            self.log(f"> {'approve' if self.approve_end else 'reject'} {approval['name']}")
            return [
                {
                    "type": "mcp_approval_response",
                    "approval_request_id": approval["id"],
                    "approve": self.approve_end,
                }
            ]
        if not pending:
            return None
        request = json.loads(pending["arguments"])["request"]
        if request["message"]:
            self.log(f"  [{request['request_type']}] {request['message']}")
        if request["request_type"] == "form":
            if request["metadata"]["form"] == "profile":
                value: dict[str, Any] = PROFILE
            else:
                value = {"skipped": True} if self.skip_feedback else FEEDBACK
        else:
            value = self._message(next(steps, "終わりにします"))
        self.log(f"> {request['request_type']}: {json.dumps(value, ensure_ascii=False)}")
        output = json.dumps(value, ensure_ascii=False)
        return [{"type": "function_call_output", "call_id": pending["call_id"], "output": output}]

    def _message(self, step: str) -> dict[str, Any]:
        if step == OPEN and self._card:
            self.current_url = self._card
            return {"text": "", "url": self.current_url, "event": "opened"}
        return {"text": step, "url": self.current_url}


def _stdin() -> Iterator[str]:
    while True:
        try:
            yield input("you> ")
        except EOFError:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("base_url", nargs="?", default="http://localhost:8088")
    parser.add_argument("steps", nargs="*", help="発言の並び (@open で案内カードを表示)")
    parser.add_argument("--token", action="store_true", help="Entra ID のトークンを付ける")
    parser.add_argument("--reject-end", action="store_true", help="終了の提案を却下する")
    parser.add_argument("--skip-feedback", action="store_true", help="アンケートをスキップする")
    parser.add_argument("--interactive", action="store_true", help="標準入力から発言を読む")
    args = parser.parse_args()

    headers, query = {}, None
    if args.token:
        from azure.identity import DefaultAzureCredential

        token = DefaultAzureCredential().get_token("https://ai.azure.com/.default").token
        headers["Authorization"] = f"Bearer {token}"
        query = {"api-version": "v1"}
    client = OpenAI(
        base_url=args.base_url, api_key="unused", default_headers=headers, default_query=query
    )
    steps = _stdin() if args.interactive else iter(args.steps or DEFAULT_STEPS)
    Driver(
        client,
        hosted=args.token,
        approve_end=not args.reject_end,
        skip_feedback=args.skip_feedback,
    ).run(steps)


if __name__ == "__main__":
    main()
