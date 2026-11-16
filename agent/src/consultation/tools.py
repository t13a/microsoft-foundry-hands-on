"""相談役 (search-assistant) のツールの実装 (基本設計書 5.2)。

探索のツールは、利用者が画面でたどるのと同じカタログを使い、実在するデータから作った URL を返す。
`propose_display` はその URL をカタログと照らし合わせてから返し、画面は結果から案内カードを描く。
ツールは状態を持たない。結果はモデルが読みやすいよう、日本語をエスケープしない JSON の文字列で返す。
"""

import json
import os
from functools import cache
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote

import catalog
from agent_framework import FunctionTool, tool
from catalog import Catalog, CategoryLocation, SearchLocation
from pydantic import Field

DATA_DIR_ENV = "CATALOG_DIR"

# 探索の結果に載せる数の上限。件数 (count) は上限に関係なく全体の数を返す。
MAX_SERVICES = 10
# 結果に載せる説明の冒頭の長さ。結果は会話の履歴として毎回モデルに送られるので、短くする。
SUMMARY_LENGTH = 60

DISPLAY_FAILED = "表示できませんでした"

# 承認が必要なツール (基本設計書 5.2)。表示提案は承認なし (DR-5)。
APPROVAL_REQUIRED = frozenset({"propose_end"})


@cache
def load_catalog(directory: Path | None = None) -> Catalog:
    """カタログを読み込む。セッションの実行環境で 1 回だけ読む (基本設計書 7.1)。"""
    if directory is None:
        env = os.environ.get(DATA_DIR_ENV)
        # The repository's data/ when run from a checkout (the deploy package sets CATALOG_DIR).
        directory = Path(env) if env else Path(__file__).resolve().parents[3] / "data"
    return catalog.load(directory)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _summary(text: str, length: int = SUMMARY_LENGTH) -> str:
    line = " ".join(text.replace("#", "").split())
    return line if len(line) <= length else line[:length] + "…"


def _url(url: str) -> str:
    """モデルに渡す URL。デコードした形の方がずっと少ないトークンで済み、propose_display が
    エンコードした決まった形に戻す (基本設計書 5.2)。"""
    return unquote(url)


def _service(service: catalog.Service) -> dict[str, Any]:
    # Contact details stay out: the agent must not answer them in chat (F-AGT-10).
    return {
        "name": service.name,
        "url": _url(catalog.category_url(service.category_path, [service.name])),
        "summary": _summary(service.description),
    }


def list_categories(data: Catalog, path: list[str] | None = None) -> dict[str, Any]:
    path = tuple(path or ())
    if path:
        parent = data.category(path)
        if parent is None:
            return {"error": "カテゴリが見つかりません", "path": list(path)}
        children = parent.children
    else:
        children = data.top
    return {
        "path": list(path),
        "categories": [
            {
                "name": c.name,
                "summary": _summary(c.description),
                "url": _url(catalog.category_url(c.path)),
            }
            for c in children
        ],
    }


def get_category(data: Catalog, path: list[str]) -> dict[str, Any]:
    category = data.category(tuple(path))
    if category is None:
        return {"error": "カテゴリが見つかりません", "path": list(path)}
    return {
        "name": category.name,
        "path": list(category.path),
        "url": _url(catalog.category_url(category.path)),
        "summary": _summary(category.description, 200),
        "children": [
            {"name": c.name, "url": _url(catalog.category_url(c.path))} for c in category.children
        ],
        "serviceCount": len(category.services),
        "services": [_service(s) for s in category.services[:MAX_SERVICES]],
    }


def search_services(data: Catalog, query: str) -> dict[str, Any]:
    services = catalog.search(data, query)
    result: dict[str, Any] = {"query": query, "count": len(services)}
    if services:
        result["url"] = _url(catalog.search_url(query))
        result["services"] = [_service(s) for s in services[:MAX_SERVICES]]
    return result


def propose_display(data: Catalog, urls: list[str]) -> dict[str, Any]:
    """URL をカタログと照らし合わせ、表示する 1 つの URL と件数を返す。

    同じカテゴリの強調表示は 1 つの URL にまとめる。照らし合わせに失敗したら、
    理由を添えて「表示できませんでした」を返し、エージェントにやり直させる。
    """

    def failed(reason: str) -> dict[str, Any]:
        return {"error": DISPLAY_FAILED, "reason": reason}

    if not urls:
        return failed("urls が空です。探索のツールが返した URL を渡してください。")
    locations = []
    for url in urls:
        location = catalog.resolve(data, url)
        if location is None:
            return failed(
                f"{url} はサイトに存在しません。探索のツールが返した URL をそのまま渡してください。"
            )
        locations.append(location)

    match locations:
        case [SearchLocation(query)]:
            return {"url": catalog.search_url(query), "count": len(catalog.search(data, query))}
        case [CategoryLocation(path), *_] if all(
            isinstance(loc, CategoryLocation) and loc.path == path for loc in locations
        ):
            highlights = list(dict.fromkeys(h for loc in locations for h in loc.highlights))
            category = data.category(path)
            assert category is not None  # resolve() で確かめ済み
            count = len(highlights) if highlights else len(category.services)
            return {"url": catalog.category_url(path, highlights), "count": count}
    return failed(
        "異なるカテゴリの URL や、カテゴリと検索結果の URL は 1 回の表示にまとめられません。"
        "1 つずつ提案してください。"
    )


def suggest_replies(options: list[str]) -> dict[str, Any]:
    return {"shown": True}


def propose_end() -> dict[str, Any]:
    return {"ended": True}


def show_emergency_contacts() -> dict[str, Any]:
    return {"shown": True}


def ended(result: Any) -> bool:
    """`propose_end` が承認されて実行された結果か。

    承認の後に再開した応答には元のツール呼び出しが含まれないので、結果そのもので判定する
    (基本設計書 4.1)。却下されたときはフレームワークが別の結果を入れる。
    """
    return _parsed(result) == propose_end()


def display_result(result: Any) -> dict[str, Any] | None:
    """`propose_display` の成功した結果なら、その中身を返す。"""
    parsed = _parsed(result)
    if isinstance(parsed, dict) and set(parsed) == {"url", "count"}:
        return parsed
    return None


def _parsed(result: Any) -> Any:
    """関数の結果 (Content の並び、または文字列) を JSON として読む。読めなければ None。"""
    if isinstance(result, list):
        result = "".join(getattr(c, "text", None) or "" for c in result)
    if not isinstance(result, str):
        return None
    try:
        return json.loads(result)
    except ValueError:
        return None


def build_tools(data: Catalog) -> list[FunctionTool]:
    """ツールを作る。要求ごとに作り直す (使い回すとホストが拒否する)。"""
    path_doc = "カテゴリパス (上の階層から順にカテゴリ名を並べる)"

    def list_categories_tool(
        path: Annotated[list[str] | None, Field(description=f"{path_doc}。空なら最上位")] = None,
    ) -> str:
        """子カテゴリの名前、説明の冒頭、URL を返す。"""
        return _json(list_categories(data, path))

    def get_category_tool(path: Annotated[list[str], Field(description=path_doc)]) -> str:
        """カテゴリの説明の全文と URL、子カテゴリ、所属サービス (強調表示つきの URL) を返す。"""
        return _json(get_category(data, path))

    def search_services_tool(
        query: Annotated[str, Field(description="検索語 (空白区切りで AND)")],
    ) -> str:
        """キーワードでサービスを検索し、一致したサービスと検索結果の URL を返す。"""
        return _json(search_services(data, query))

    def propose_display_tool(
        urls: Annotated[list[str], Field(description="探索のツールが返した URL をそのまま並べる")],
    ) -> str:
        """見つかった内容の案内カードを出す。表示する URL と件数を返す。"""
        return _json(propose_display(data, urls))

    def suggest_replies_tool(
        options: Annotated[list[str], Field(description="推奨する選択肢の文言")],
    ) -> str:
        """利用者に推奨の選択肢を示す。"""
        return _json(suggest_replies(options))

    def propose_end_tool() -> str:
        """相談を終了してよいか、利用者に確認する。"""
        return _json(propose_end())

    def show_emergency_contacts_tool() -> str:
        """緊急時の相談先の定型の案内を表示する。"""
        return _json(show_emergency_contacts())

    functions = {
        "list_categories": list_categories_tool,
        "get_category": get_category_tool,
        "search_services": search_services_tool,
        "propose_display": propose_display_tool,
        "suggest_replies": suggest_replies_tool,
        "propose_end": propose_end_tool,
        "show_emergency_contacts": show_emergency_contacts_tool,
    }
    return [
        tool(
            fn,
            name=name,
            approval_mode="always_require" if name in APPROVAL_REQUIRED else "never_require",
        )
        for name, fn in functions.items()
    ]
