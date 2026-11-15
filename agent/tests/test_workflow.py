"""スタブのモードで、ホストの Responses の受け口を通して相談を最初から最後まで動かす。"""

import json
import shutil
from urllib.parse import unquote

import catalog
import pytest
from consultation import content, workflow
from consultation.drive import OPEN, Driver, Turn
from consultation.server import create_server
from openai import OpenAI
from starlette.testclient import TestClient

TEXTS = content.load()
FOUND_FLOW = ["子どもの予防接種について知りたい", OPEN, "見つかった", "ない"]
PATH = ("子育て・教育", "健診・予防接種", "予防接種")


@pytest.fixture
def events(monkeypatch):
    recorded: list[tuple[str, dict]] = []
    original = workflow.record

    def record(name, session_id, **attributes):
        assert session_id
        recorded.append((name, attributes))
        original(name, session_id, **attributes)

    monkeypatch.setattr(workflow, "record", record)
    return recorded


@pytest.fixture
def consult(monkeypatch):
    def run(steps, scenario=None, **options) -> list[Turn]:
        if scenario:
            monkeypatch.setenv("STUB_SCENARIO", scenario)
        # テストではトレースの出力 (既定はコンソール) を設定しない。
        with TestClient(create_server(configure_observability=None)) as http:
            client = OpenAI(base_url="http://testserver", api_key="unused", http_client=http)
            return Driver(client, log=lambda _: None, **options).run(iter(steps))

    return run


def cards(turns: list[Turn]) -> list[dict]:
    return [o for t in turns for o in t.outputs("propose_display")]


def requests(turn: Turn) -> list[dict]:
    return [json.loads(c["arguments"])["request"] for c in turn.calls("request_info")]


def options(turn: Turn) -> list[list[str]]:
    return [json.loads(c["arguments"])["options"] for c in turn.calls("suggest_replies")]


def test_found_flow_from_greeting_to_thanks(consult, events):
    turns = consult(FOUND_FLOW)
    greeting, profile, search, opened, found, end, approval, feedback = turns

    assert "お名前や連絡先は書かずにご相談ください" in greeting.text
    [form] = requests(greeting)
    assert form["request_type"] == "form"
    assert form["metadata"]["form"] == "profile"
    assert form["metadata"]["schema"]["properties"]["ward"]["enum"][-2:] == ["市外", "無回答"]

    assert requests(profile)[0]["request_type"] == "user_message"

    # 見つかったら「見つかりました」とだけ書き、案内カードを出す (確認の質問をしない)。
    expected = catalog.category_url(PATH, ["予防接種相談窓口"])
    assert search.outputs("propose_display") == [{"url": expected, "count": 1}]
    assert search.text.endswith("見つかりました。")
    assert "表示しますか" not in search.text
    assert search.calls("propose_display")  # 承認なし: 結果がすぐ届く
    assert not [i for i in search.items if i["type"] == "mcp_approval_request"]

    # 案内カードから表示したら、見つかったかを聞き、選択肢を出す。
    assert "見つかりましたか" in opened.text
    assert options(opened)[0][0] == "見つかった"
    assert "ほかにお探し" not in opened.text

    # 「見つかった」の後にだけ、ほかに探しているものを聞く。
    assert "ほかにお探しのものはありますか" in found.text

    # 終了の提案は承認が要る。
    assert [i["name"] for i in end.items if i["type"] == "mcp_approval_request"] == ["propose_end"]
    assert [r["metadata"]["form"] for r in requests(approval)] == ["feedback"]
    assert requests(approval)[0]["metadata"]["skippable"] is True

    assert feedback.text == TEXTS.thanks
    assert not requests(feedback)  # 待ち受けのないまま完了

    assert [name for name, _ in events] == [
        "consultation.started",
        "consultation.profile",
        "consultation.display_proposed",
        "consultation.display_opened",
        "consultation.ended",
        "consultation.feedback",
    ]
    attributes = dict(events)
    assert attributes["consultation.profile"]["profile.ward"] == "中央区"
    assert attributes["consultation.display_proposed"] == {"url": expected, "count": 1}
    assert attributes["consultation.display_opened"] == {"url": expected}
    assert attributes["consultation.ended"] == {"reason": "propose_end", "turns": 4}
    assert attributes["consultation.feedback"]["feedback.rating"] == 5


def test_the_agent_receives_profile_url_and_opened_event(consult, monkeypatch):
    received: list[str] = []
    original = workflow.compose_message

    def compose(*args):
        received.append(original(*args))
        return received[-1]

    monkeypatch.setattr(workflow, "compose_message", compose)
    consult(FOUND_FLOW)

    first, opened, found, _ = received
    assert "性別: 無回答、年代: 30代、お住まいの区: 中央区" in first
    assert f"{workflow.URL_LABEL} /" in first
    assert workflow.EVENT_LABEL not in first
    assert first.endswith("子どもの予防接種について知りたい")
    page = "/c/" + "/".join(PATH) + "#svc=予防接種相談窓口"
    assert f"{workflow.URL_LABEL} {page}" in opened  # デコードして添える
    assert f"{workflow.EVENT_LABEL} {workflow.OPENED_NOTE}" in opened
    assert opened.endswith(workflow.TEXT_LABEL + " ")  # 本文は空
    assert workflow.EVENT_LABEL not in found


def test_compose_message():
    schema = TEXTS.profile_schema
    profile = {"gender": "女性", "age": "40代", "ward": "北区"}
    reply = {"text": "ごみの出し方", "url": "/search?q=%E3%81%94%E3%81%BF"}
    assert workflow.compose_message(profile, schema, reply).splitlines() == [
        f"{workflow.PROFILE_LABEL} 性別: 女性、年代: 40代、お住まいの区: 北区",
        f"{workflow.URL_LABEL} /search?q=ごみ",
        f"{workflow.TEXT_LABEL} ごみの出し方",
    ]


def test_multiple_highlights_are_merged_into_one_card(consult):
    turns = consult(FOUND_FLOW, scenario="multiple")
    [card] = cards(turns)
    assert card == {
        "url": catalog.category_url(PATH, ["予防接種相談窓口", "定期予防接種"]),
        "count": 2,
    }


def test_fabricated_url_is_rejected_and_retried(consult, events):
    turns = consult(FOUND_FLOW, scenario="fabricated")
    failed, shown = cards(turns)
    assert failed["error"] == "表示できませんでした"
    assert shown["url"] == catalog.category_url(PATH, ["予防接種相談窓口"])
    # カードになるのは照らし合わせに通ったものだけ。
    assert [a["url"] for n, a in events if n == "consultation.display_proposed"] == [shown["url"]]


def test_category_scenario_shows_a_category(consult):
    [card] = cards(consult(FOUND_FLOW, scenario="category"))
    assert unquote(card["url"]) == "/c/子育て・教育/健診・予防接種/予防接種"
    assert card["count"] == 3


def test_search_scenario_shows_search_results(consult):
    [card] = cards(consult(FOUND_FLOW, scenario="search"))
    assert card == {"url": catalog.search_url("予防接種"), "count": 4}


def test_not_found_leads_to_general_information(consult):
    turns = consult(["今日の天気を教えて", OPEN, "見つかった", "ない"])
    [card] = cards(turns)
    assert unquote(card["url"]) == "/c/届出・証明/総合案内#svc=総合案内窓口"


def test_emergency_shows_contacts(consult):
    turns = consult(["死にたい", *FOUND_FLOW])
    assert turns[2].calls("show_emergency_contacts")
    assert turns[-1].text == TEXTS.thanks


@pytest.mark.parametrize("scenario", ["content_filter", "content_filter_error"])
def test_content_filter_returns_a_fixed_message_and_waits(consult, events, scenario):
    turns = consult(["死にたい", *FOUND_FLOW], scenario=scenario)
    blocked = turns[2]
    assert TEXTS.content_filtered in blocked.text
    assert "110" in blocked.text and "119" in blocked.text
    assert requests(blocked)[0]["request_type"] == "user_message"
    assert "consultation.content_filtered" in [name for name, _ in events]
    # 遮断の後も相談を続けられる。
    assert cards(turns)
    assert turns[-1].text == TEXTS.thanks


def test_rejecting_the_end_continues_the_consultation(consult, events):
    turns = consult([*FOUND_FLOW, "終わりにします"], reject_end=1)
    rejected = turns[6]
    assert "ほかにお探しのものがあれば" in rejected.text
    assert requests(rejected)[0]["request_type"] == "user_message"
    assert turns[-1].text == TEXTS.thanks
    assert dict(events)["consultation.ended"] == {"reason": "propose_end", "turns": 5}


def test_feedback_can_be_skipped(consult, events):
    turns = consult(FOUND_FLOW, skip_feedback=True)
    assert turns[-1].text == TEXTS.thanks
    assert dict(events)["consultation.feedback"] == {"feedback.skipped": True}


def test_turn_limit_ends_the_consultation(consult, events, monkeypatch, tmp_path):
    directory = tmp_path / "content"
    shutil.copytree(content.DEFAULT_CONTENT_DIR, directory)
    messages = directory / "messages.toml"
    messages.write_text(
        messages.read_text(encoding="utf-8").replace("max_turns = 30", "max_turns = 2"),
        encoding="utf-8",
    )
    monkeypatch.setenv(content.CONTENT_DIR_ENV, str(directory))
    content.load.cache_clear()
    try:
        turns = consult(["予防接種", "別の条件で探したい", "見つかった"])
    finally:
        content.load.cache_clear()
    limit = turns[3]
    assert TEXTS.turn_limit in limit.text
    assert [r["metadata"]["form"] for r in requests(limit)] == ["feedback"]
    assert dict(events)["consultation.ended"] == {"reason": "turn_limit", "turns": 2}
