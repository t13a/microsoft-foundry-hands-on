"""ローカル用のスタブのチャットクライアント (F-DEV-04、基本設計書 V-4)。

実際のモデルの代わりに、直前のメッセージから次の一手を台本どおりに決める。
流れと画面の確認用で、エージェントの品質の確認には使わない (F-DEV-07)。
ツールは本物を呼ぶので、URL はカタログから作られる。

台本 (シナリオ) は `STUB_SCENARIO` か引数で選ぶ:

- `default`: キーワードで検索し、最初のサービスを案内カードにする。
- `category`: カテゴリを上からたどり、サービスのあるカテゴリを案内カードにする。
- `multiple`: 検索で見つかった同じカテゴリのサービスを 2 つまとめて案内カードにする。
- `search`: 検索結果のページを案内カードにする。
- `fabricated`: 最初は存在しない URL を作り出して表示提案し、弾かれたらやり直す。
- `content_filter`: 緊急の言葉を含む発言で、応答がコンテンツフィルターで遮断される (未完了)。
- `content_filter_error`: 緊急の言葉を含む発言で、要求がコンテンツフィルターで弾かれる (例外)。

どの台本でも、発言に応じて次のように進む: 案内カードから表示した (opened) → 「見つかりましたか？」と
選択肢、「見つかった」→「ほかにお探しのものは？」と選択肢、「ない」「終わり」→ 終了の提案、
緊急の言葉 → 緊急時の案内 (遮断の台本を除く)。
"""

import json
import os
import uuid
from collections.abc import Sequence
from typing import Any

from agent_framework import (
    BaseChatClient,
    ChatResponse,
    ChatResponseUpdate,
    Content,
    FunctionInvocationLayer,
    Message,
    ResponseStream,
)
from agent_framework.exceptions import ChatClientContentFilterException

from consultation.workflow import EVENT_LABEL, OPENED_NOTE, TEXT_LABEL

SCENARIO_ENV = "STUB_SCENARIO"
SCENARIOS = (
    "default",
    "category",
    "multiple",
    "search",
    "fabricated",
    "content_filter",
    "content_filter_error",
)

# 発言から検索語を選ぶための語。どれも含まなければ発言をそのまま検索する。
KEYWORDS = ("予防接種", "健診", "検診", "保育", "子育て", "ごみ", "住民票", "戸籍", "相談")
GENERAL_INFORMATION = "総合案内"
EMERGENCY_WORDS = ("死にたい", "助けて", "暴力", "救急", "倒れ")

FOUND = "見つかった"
FOUND_OPTIONS = [FOUND, "別の条件で探したい", "電話で相談したい", "カテゴリから探し直す"]
MORE_OPTIONS = ["ない", "ほかにも探したい"]
FABRICATED_URL = "/c/暮らし/存在しないカテゴリ#svc=架空のサービス"
FILTERED_TEXT = "I'm sorry, but I cannot assist with that request."


def _call(name: str, **arguments: Any) -> Content:
    return Content.from_function_call(f"{name}-{uuid.uuid4().hex[:8]}", name, arguments=arguments)


def _text(text: str) -> Content:
    return Content.from_text(text)


def _parsed(result: Any) -> Any:
    if isinstance(result, list):
        result = "".join(getattr(c, "text", None) or "" for c in result)
    try:
        return json.loads(result) if isinstance(result, str) else result
    except ValueError:
        return result


def _labeled(text: str, label: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(label):
            return line.removeprefix(label).strip()
    return None


class ScriptedChatClient(FunctionInvocationLayer, BaseChatClient):
    """直前のメッセージから次の一手を決める、台本どおりの小さなモデル。"""

    def __init__(self, scenario: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.scenario = scenario or os.environ.get(SCENARIO_ENV) or "default"
        if self.scenario not in SCENARIOS:
            raise ValueError(f"unknown stub scenario: {self.scenario} (one of {SCENARIOS})")

    # 台本

    def _next(self, messages: Sequence[Message]) -> tuple[list[Content], str | None]:
        """次に返す内容と終了理由。"""
        last = messages[-1]
        results = [c for c in last.contents if c.type == "function_result"]
        if results:
            calls = {
                c.call_id: c for m in messages for c in m.contents if c.type == "function_call"
            }
            call = calls.get(results[-1].call_id)
            name = call.name if call else None
            return self._after_tool(name, _parsed(results[-1].result), messages), None
        return self._after_user(last.text or "")

    def _after_user(self, message: str) -> tuple[list[Content], str | None]:
        text = _labeled(message, TEXT_LABEL)
        text = message if text is None else text
        if _labeled(message, EVENT_LABEL) == OPENED_NOTE:
            return [
                _text("お探しのものは見つかりましたか？"),
                _call("suggest_replies", options=FOUND_OPTIONS),
            ], None
        if any(word in text for word in EMERGENCY_WORDS):
            # 技術検証 (V-6) では、自殺をほのめかす発言がコンテンツフィルターで遮断された。
            if self.scenario == "content_filter":
                return [_text(FILTERED_TEXT)], "content_filter"
            if self.scenario == "content_filter_error":
                raise ChatClientContentFilterException(
                    "The prompt was blocked by the content filter"
                )
            return [_text("緊急の相談先をご案内します。"), _call("show_emergency_contacts")], None
        if text.strip() == FOUND:
            return [
                _text("よかったです。ほかにお探しのものはありますか？"),
                _call("suggest_replies", options=MORE_OPTIONS),
            ], None
        if text.strip() == "ない" or "終わ" in text or "大丈夫" in text:
            return [_call("propose_end")], None
        if "見つからな" in text or "別の条件" in text:
            return [_text("承知しました。別の言葉で、お探しのものを教えてください。")], None
        if "電話" in text:
            return [
                _text("お調べします。"),
                _call("search_services", query=GENERAL_INFORMATION),
            ], None
        if self.scenario == "category" or "カテゴリ" in text:
            return [_text("カテゴリからお調べします。"), _call("list_categories", path=[])], None
        query = next((word for word in KEYWORDS if word in text), text)
        return [_text("お調べします。"), _call("search_services", query=query)], None

    def _after_tool(
        self, name: str | None, result: Any, messages: Sequence[Message]
    ) -> list[Content]:
        match name:
            case "search_services":
                return self._after_search(result, messages)
            case "list_categories":
                categories = result.get("categories") or []
                if not categories:
                    return [_text("カテゴリが見つかりませんでした。")]
                return [_call("get_category", path=[*result["path"], categories[0]["name"]])]
            case "get_category":
                if result.get("services"):
                    return [_call("propose_display", urls=[result["url"]])]
                if result.get("children"):
                    child = result["children"][0]["name"]
                    return [_call("get_category", path=[*result["path"], child])]
                return [_text("このカテゴリにはサービスがありませんでした。")]
            case "propose_display":
                if "url" in result:
                    return [_text("見つかりました。")]
                retry = self._last_found_url(messages)
                if retry:
                    return [_call("propose_display", urls=[retry])]
                return [_text("うまくご案内できませんでした。")]
            case "propose_end":
                if result == {"ended": True}:
                    return [_text("ご相談ありがとうございました。")]
                return [_text("承知しました。ほかにお探しのものがあれば、どうぞ。")]
            case "suggest_replies" | "show_emergency_contacts":
                return []
        return [_text("（台本にない状態です）")]

    def _after_search(self, result: dict[str, Any], messages: Sequence[Message]) -> list[Content]:
        services = result.get("services") or []
        if not services:
            if result.get("query") != GENERAL_INFORMATION:
                return [_call("search_services", query=GENERAL_INFORMATION)]
            return [_text("該当するサービスが見つかりませんでした。")]
        if self.scenario == "fabricated" and not self._proposed(messages):
            return [_call("propose_display", urls=[FABRICATED_URL])]
        if self.scenario == "search":
            return [_call("propose_display", urls=[result["url"]])]
        if self.scenario == "multiple":
            path = services[0]["url"].split("#")[0]
            same = [s["url"] for s in services if s["url"].split("#")[0] == path][:2]
            return [_call("propose_display", urls=same)]
        return [_call("propose_display", urls=[services[0]["url"]])]

    @staticmethod
    def _proposed(messages: Sequence[Message]) -> bool:
        return any(
            c.type == "function_call" and c.name == "propose_display"
            for m in messages
            for c in m.contents
        )

    @staticmethod
    def _last_found_url(messages: Sequence[Message]) -> str | None:
        calls = {
            c.call_id: c.name for m in messages for c in m.contents if c.type == "function_call"
        }
        for m in reversed(messages):
            for c in m.contents:
                if c.type == "function_result" and calls.get(c.call_id) == "search_services":
                    services = _parsed(c.result).get("services") or []
                    if services:
                        return services[0]["url"]
        return None

    # チャットクライアント

    def _inner_get_response(self, *, messages, stream, options, **kwargs):
        contents, finish_reason = self._next(list(messages))
        if stream:

            async def _stream():
                for content in contents:
                    if content.type == "text":
                        # 画面で少しずつ届く様子が見えるよう、文章を分けて送る。
                        for i in range(0, len(content.text), 6):
                            chunk = Content.from_text(content.text[i : i + 6])
                            yield ChatResponseUpdate(role="assistant", contents=[chunk])
                    else:
                        yield ChatResponseUpdate(role="assistant", contents=[content])
                if finish_reason:
                    yield ChatResponseUpdate(
                        role="assistant", contents=[], finish_reason=finish_reason
                    )

            return ResponseStream(_stream(), finalizer=ChatResponse.from_updates)

        async def _response():
            message = Message(role="assistant", contents=contents)
            return ChatResponse(messages=[message], finish_reason=finish_reason)

        return _response()
