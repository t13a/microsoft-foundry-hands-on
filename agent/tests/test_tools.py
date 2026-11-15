import asyncio
import json
from pathlib import Path
from urllib.parse import quote

import catalog
import pytest
from consultation import tools

from .conftest import FIXTURE_DATA

PATH = ("子育て・教育", "健診・予防接種", "予防接種")
CATEGORY = "/c/" + "/".join(PATH)
ENCODED = catalog.category_url(PATH)
PROMPT_AGENT = Path(__file__).resolve().parents[1] / "prompt-agent"


@pytest.fixture
def data():
    return tools.load_catalog(FIXTURE_DATA)


def test_search_services_returns_urls_of_existing_pages(data):
    result = tools.search_services(data, "予防接種")
    assert result["count"] == 4
    assert result["url"] == catalog.search_url("予防接種")
    first = result["services"][0]
    assert first["name"] == "予防接種相談窓口"
    assert first["categoryPath"] == list(PATH)
    assert first["url"] == catalog.category_url(PATH, ["予防接種相談窓口"])
    assert all(catalog.resolve(data, s["url"]) for s in result["services"])


def test_search_services_without_hits_has_no_url(data):
    assert tools.search_services(data, "存在しない語") == {"query": "存在しない語", "count": 0}


def test_list_categories(data):
    top = tools.list_categories(data)
    assert [c["name"] for c in top["categories"]][:2] == ["子育て・教育", "健康・医療"]
    assert top["categories"][0]["url"] == catalog.category_url(("子育て・教育",))
    assert all(len(c["description"]) <= tools.SUMMARY_LENGTH + 1 for c in top["categories"])
    children = tools.list_categories(data, ["子育て・教育"])
    assert "健診・予防接種" in [c["name"] for c in children["categories"]]
    assert "error" in tools.list_categories(data, ["存在しない"])


def test_get_category(data):
    result = tools.get_category(data, list(PATH))
    assert result["url"] == ENCODED
    assert result["children"] == []
    assert [s["name"] for s in result["services"]] == [
        "予防接種相談窓口",
        "定期予防接種",
        "任意予防接種費用助成",
    ]
    assert result["services"][1]["url"] == catalog.category_url(PATH, ["定期予防接種"])
    assert "error" in tools.get_category(data, ["存在しない"])


def test_propose_display_returns_the_encoded_url_and_count(data):
    url = catalog.category_url(PATH, ["定期予防接種"])
    assert tools.propose_display(data, [url]) == {"url": url, "count": 1}


@pytest.mark.parametrize(
    "url",
    [
        f"{CATEGORY}#svc=定期予防接種",  # デコードした形
        f"{ENCODED}#svc={quote('定期予防接種')}",  # エンコードした形
        f"/c/{quote(PATH[0])}/{PATH[1]}/{PATH[2]}#svc=定期予防接種",  # 混在
        f" {CATEGORY}/#svc=定期予防接種",  # 前後の空白、末尾のスラッシュ
    ],
)
def test_propose_display_absorbs_encoding_differences(data, url):
    expected = catalog.category_url(PATH, ["定期予防接種"])
    assert tools.propose_display(data, [url]) == {"url": expected, "count": 1}


@pytest.mark.parametrize(
    "urls",
    [
        [],
        ["/c/子育て・教育/存在しないカテゴリ"],
        [f"{CATEGORY}#svc=存在しないサービス"],
        ["/search?q=存在しない語"],
        ["https://www.example.com/kosodate/yobou"],
        [f"{CATEGORY}#svc=定期予防接種", "/c/子育て・教育/作り出したカテゴリ#svc=架空"],
    ],
)
def test_propose_display_rejects_fabricated_urls(data, urls):
    result = tools.propose_display(data, urls)
    assert result["error"] == tools.DISPLAY_FAILED
    assert result["reason"]


def test_propose_display_merges_highlights_in_the_same_category(data):
    result = tools.propose_display(
        data,
        [
            catalog.category_url(PATH, ["予防接種相談窓口"]),
            f"{CATEGORY}#svc=定期予防接種",
            f"{CATEGORY}#svc=予防接種相談窓口",  # 重複はまとめる
            CATEGORY,  # 強調表示のない同じカテゴリ
        ],
    )
    assert result == {
        "url": catalog.category_url(PATH, ["予防接種相談窓口", "定期予防接種"]),
        "count": 2,
    }
    assert result["url"].endswith(f"#svc={quote('予防接種相談窓口')}&svc={quote('定期予防接種')}")


@pytest.mark.parametrize(
    "urls",
    [
        [f"{CATEGORY}#svc=定期予防接種", "/c/子育て・教育/健診・予防接種/乳幼児健診"],
        [f"{CATEGORY}#svc=定期予防接種", "/search?q=予防接種"],
        ["/search?q=予防接種", "/search?q=健診"],
    ],
)
def test_propose_display_does_not_mix_pages(data, urls):
    assert tools.propose_display(data, urls)["error"] == tools.DISPLAY_FAILED


def test_propose_display_of_a_category_or_search(data):
    assert tools.propose_display(data, [CATEGORY]) == {"url": ENCODED, "count": 3}
    assert tools.propose_display(data, ["/search?q=予防接種"]) == {
        "url": catalog.search_url("予防接種"),
        "count": 4,
    }


def test_results_are_read_back_from_the_tool_output():
    assert tools.ended(json.dumps({"ended": True}))
    assert not tools.ended("Error: Tool call invocation was rejected by user.")
    assert tools.display_result('{"url": "/c/a", "count": 1}') == {"url": "/c/a", "count": 1}
    assert tools.display_result('{"error": "表示できませんでした", "reason": "…"}') is None


def test_tools_return_json_without_escaping(data):
    by_name = {t.name: t for t in tools.build_tools(data)}
    assert set(by_name) == {
        "list_categories",
        "get_category",
        "search_services",
        "propose_display",
        "suggest_replies",
        "propose_end",
        "show_emergency_contacts",
    }
    assert [n for n, t in by_name.items() if t.approval_mode == "always_require"] == ["propose_end"]
    invoke = by_name["search_services"].invoke(arguments={"query": "予防接種"})
    result = asyncio.run(invoke)
    text = "".join(c.text for c in result)
    assert "予防接種相談窓口" in text
    assert json.loads(text)["count"] == 4


def test_tools_are_created_per_request(data):
    first, second = tools.build_tools(data), tools.build_tools(data)
    assert all(a is not b for a, b in zip(first, second, strict=True))
