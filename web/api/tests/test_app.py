from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient
from web_api.app import create_app

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
