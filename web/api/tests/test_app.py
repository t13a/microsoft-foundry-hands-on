import json
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from fastapi.testclient import TestClient
from web_api.app import create_app
from web_api.relay import RateLimiter, RelaySettings

SMALL = Path(__file__).parents[3] / "packages/catalog/tests/fixtures/small"


@pytest.fixture
def static(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html>spa", encoding="utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(static: Path):
    with TestClient(create_app(SMALL, static)) as c:
        yield c


def test_top_categories(client):
    body = client.get("/api/categories").json()
    names = [c["name"] for c in body["categories"]]
    assert names == ["子育て・教育", "健康・医療", "住まい・暮らし", "届出・証明"]
    assert body["categories"][0]["children"] == ["健診・予防接種", "保育・幼稚園", "相談窓口"]


def test_category_page_accepts_encoded_path(client):
    body = client.get("/api/categories/子育て・教育/健診・予防接種/予防接種").json()
    assert body["name"] == "予防接種"
    assert [b["name"] for b in body["breadcrumbs"]] == ["子育て・教育", "健診・予防接種"]
    assert body["services"][0]["name"] == "予防接種相談窓口"
    assert unquote(body["services"][0]["pageUrl"]) == (
        "/c/子育て・教育/健診・予防接種/予防接種#svc=予防接種相談窓口"
    )
    encoded = client.get(body["url"].replace("/c/", "/api/categories/", 1)).json()
    assert encoded["name"] == "予防接種"


def test_unknown_category_is_404(client):
    assert client.get("/api/categories/存在しない").status_code == 404
    assert client.get("/api/nothing").status_code == 404


def test_search(client):
    body = client.get("/api/search", params={"q": "がん　検診"}).json()
    assert body["count"] == 2
    assert body["services"][0]["categoryPath"] == ["健康・医療", "検診", "がん検診"]


def test_serves_spa_with_fallback(client):
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/c/子育て・教育").text == "<!doctype html>spa"
    assert client.get("/").text == "<!doctype html>spa"
    assert client.get("/../pyproject.toml").text == "<!doctype html>spa"


def test_basic_auth(static):
    with TestClient(create_app(SMALL, static, basic_auth=("demo", "secret"))) as c:
        denied = c.get("/")
        assert denied.status_code == 401
        assert "Basic" in denied.headers["www-authenticate"]
        assert c.get("/api/categories", auth=("demo", "wrong")).status_code == 401
        assert c.get("/api/categories", auth=("demo", "secret")).status_code == 200


def test_invalid_catalog_stops_startup(tmp_path, static):
    (tmp_path / "data").mkdir()
    with pytest.raises(Exception, match="ファイルがありません"):
        with TestClient(create_app(tmp_path / "data", static)):
            pass


# --- Responses relay ---


def upstream_recorder():
    seen: list[dict] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.content)})
        if json.loads(request.content).get("input") == "boom":
            return httpx.Response(400, json={"error": {"message": "bad"}})
        stream = b'event: response.created\ndata: {"type":"response.created"}\n\n'
        return httpx.Response(
            200, stream=httpx.ByteStream(stream), headers={"content-type": "text/event-stream"}
        )

    return seen, httpx.AsyncClient(transport=httpx.MockTransport(handle))


def relay_client(static, **settings):
    seen, upstream = upstream_recorder()
    app = create_app(SMALL, static, relay=RelaySettings(**settings), agent_client=upstream)
    return seen, TestClient(app)


def test_relay_streams_and_keeps_only_allowed_fields(static):
    seen, client = relay_client(static, url="http://agent/responses")
    with client:
        response = client.post(
            "/api/responses",
            json={
                "input": "start",
                "agent_session_id": "abc",
                "previous_response_id": None,
                "model": "other-model",
                "tools": [{"type": "web_search"}],
            },
        )
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "response.created" in response.text
    assert seen == [
        {
            "url": "http://agent/responses",
            "body": {"input": "start", "agent_session_id": "abc", "stream": True},
        }
    ]


def test_relay_leaves_the_first_session_to_the_platform(static):
    seen, client = relay_client(static, platform_sessions=True)
    with client:
        client.post("/api/responses", json={"input": "start", "agent_session_id": "own"})
        client.post(
            "/api/responses",
            json={"input": [], "agent_session_id": "platform", "previous_response_id": "r1"},
        )
    assert "agent_session_id" not in seen[0]["body"]
    assert seen[1]["body"]["agent_session_id"] == "platform"


def test_relay_passes_errors_through(static):
    _, client = relay_client(static)
    with client:
        response = client.post("/api/responses", json={"input": "boom"})
    assert response.status_code == 400
    assert response.json() == {"error": {"message": "bad"}}


def test_relay_limits_requests_per_ip(static):
    _, client = relay_client(static, rate_limit_per_minute=2)
    with client:
        codes = [
            client.post(
                "/api/responses", json={"input": "x"}, headers={"x-forwarded-for": "1.1.1.1"}
            ).status_code
            for _ in range(3)
        ]
        other = client.post(
            "/api/responses", json={"input": "x"}, headers={"x-forwarded-for": "2.2.2.2"}
        )
    assert codes == [200, 200, 429]
    assert other.status_code == 200


def test_rate_limiter_forgets_after_a_minute():
    now = [0.0]
    limiter = RateLimiter(1, clock=lambda: now[0])
    assert limiter.allow("a") and not limiter.allow("a")
    now[0] = 60
    assert limiter.allow("a")
