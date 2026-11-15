import shutil
from pathlib import Path

import pytest
from catalog import (
    CategoryLocation,
    InvalidCatalogError,
    SearchLocation,
    category_url,
    load,
    parse,
    resolve,
    search,
    search_url,
    validate,
)
from catalog.cli import main

SMALL = Path(__file__).parent / "fixtures" / "small"
CATEGORY_HEADER = "階層1,階層2,階層3,説明\n"
SERVICE_HEADER = "階層1,階層2,階層3,名称,説明,住所,電話番号,ホームページURL\n"


@pytest.fixture(scope="module")
def catalog():
    return load(SMALL)


def write(directory: Path, categories: str, services: str = "") -> Path:
    (directory / "categories.csv").write_text(CATEGORY_HEADER + categories, encoding="utf-8-sig")
    (directory / "services.csv").write_text(SERVICE_HEADER + services, encoding="utf-8-sig")
    return directory


def reasons(directory: Path) -> list[str]:
    return [f"{v.file}:{v.line}: {v.reason}" for v in validate(directory)]


# --- loading ---


def test_loads_tree_in_csv_order(catalog):
    assert [c.name for c in catalog.top] == [
        "子育て・教育",
        "健康・医療",
        "住まい・暮らし",
        "届出・証明",
    ]
    kosodate = catalog.category(("子育て・教育",))
    assert [c.name for c in kosodate.children] == ["健診・予防接種", "保育・幼稚園", "相談窓口"]
    yobou = catalog.category(("子育て・教育", "健診・予防接種", "予防接種"))
    assert [s.name for s in yobou.services] == [
        "予防接種相談窓口",
        "定期予防接種",
        "任意予防接種費用助成",
    ]


def test_same_name_under_different_parents(catalog):
    # F-DAT-11, F-DAT-44
    assert catalog.category(("子育て・教育", "相談窓口")) is not None
    assert catalog.category(("健康・医療", "相談窓口")) is not None


def test_leaf_at_second_level_and_multiline_description(catalog):
    assert catalog.category(("届出・証明", "総合案内")).services[0].name == "総合案内窓口"
    assert "## 主な内容" in catalog.category(("子育て・教育",)).description


def test_parent_may_follow_children(tmp_path):
    write(tmp_path, "A,B,,子\nA,,,親\n")
    assert [c.name for c in load(tmp_path).top[0].children] == ["B"]


# --- validation ---


def test_reports_every_violation_with_file_and_line(tmp_path):
    write(
        tmp_path,
        "A,,,\nA,B,,\nA,B,,重複\n,C,,\nX,Y,,\nA,B,D/E,\n",
        "A,,,親に所属,,,,\nA,B,,s1,,,,\nA,B,,s1,,,,\nA,Z,,不明,,,,\nA,B,,,,,,\n",
    )
    assert reasons(tmp_path) == [
        "categories.csv:4: カテゴリが重複しています: A > B",
        "categories.csv:5: 上の階層が空のまま、下の階層が書かれています",
        "categories.csv:7: カテゴリ名に「/」は使えません",
        "categories.csv:6: 親カテゴリがありません: X",
        "services.csv:2: 末端ではないカテゴリです: A",
        "services.csv:4: 同じカテゴリに同じ名称があります: s1",
        "services.csv:5: カテゴリがありません: A > Z",
        "services.csv:6: 名称が空です",
    ]
    with pytest.raises(InvalidCatalogError) as error:
        load(tmp_path)
    assert len(error.value.violations) == 8


def test_line_numbers_count_multiline_records(tmp_path):
    write(tmp_path, 'A,,,"1行目\n2行目"\nA,,,重複\n')
    assert reasons(tmp_path) == ["categories.csv:4: カテゴリが重複しています: A"]


def test_wrong_header_and_missing_file(tmp_path):
    (tmp_path / "categories.csv").write_text("名前,説明\nA,x\n", encoding="utf-8")
    assert reasons(tmp_path) == [
        "categories.csv:1: 列が違います (期待する列: 階層1, 階層2, 階層3, 説明)",
        "services.csv:0: ファイルがありません",
    ]


def test_small_fixture_is_valid():
    assert validate(SMALL) == []


# --- search ---


def test_search_matches_all_terms_ignoring_width_and_case(catalog):
    assert [s.name for s in search(catalog, "予防接種　相談")] == ["予防接種相談窓口"]
    assert [s.name for s in search(catalog, "ＥＸＡＭＰＬＥ.com/GOMI")] == [
        "家庭ごみの分け方相談",
        "粗大ごみ受付センター",
    ]


def test_search_covers_category_names_and_contacts(catalog):
    assert {s.name for s in search(catalog, "乳幼児健診")} == {"乳幼児健康診査"}
    assert [s.name for s in search(catalog, "000-123-4500")] == ["総合案内窓口"]


def test_empty_query_returns_nothing(catalog):
    assert search(catalog, "  ") == []


# --- urls ---


def test_builds_encoded_urls():
    path = ("子育て・教育", "健診・予防接種", "予防接種")
    assert category_url(path) == (
        "/c/%E5%AD%90%E8%82%B2%E3%81%A6%E3%83%BB%E6%95%99%E8%82%B2"
        "/%E5%81%A5%E8%A8%BA%E3%83%BB%E4%BA%88%E9%98%B2%E6%8E%A5%E7%A8%AE"
        "/%E4%BA%88%E9%98%B2%E6%8E%A5%E7%A8%AE"
    )
    assert category_url(("A",), ["x y", "z&w"]) == "/c/A#svc=x%20y&svc=z%26w"
    assert search_url("予防 接種") == "/search?q=%E4%BA%88%E9%98%B2%20%E6%8E%A5%E7%A8%AE"


@pytest.mark.parametrize(
    "url",
    [
        category_url(("子育て・教育", "健診・予防接種", "予防接種"), ["予防接種相談窓口"]),
        "/c/子育て・教育/健診・予防接種/予防接種#svc=予防接種相談窓口",
        "/c/子育て・教育/健診・予防接種/予防接種/#svc=%E4%BA%88%E9%98%B2%E6%8E%A5%E7%A8%AE"
        "%E7%9B%B8%E8%AB%87%E7%AA%93%E5%8F%A3",
    ],
)
def test_parses_encoded_and_decoded_urls(url):
    assert parse(url) == CategoryLocation(
        ("子育て・教育", "健診・予防接種", "予防接種"), ("予防接種相談窓口",)
    )


def test_round_trips_through_parse():
    location = CategoryLocation(("A", "B/C?"), ("x&y", "z"))
    assert parse(location.url) == CategoryLocation(("A", "B", "C?"), ("x&y", "z"))
    assert parse(SearchLocation("a&b c").url) == SearchLocation("a&b c")


@pytest.mark.parametrize(
    "url", ["/", "/c/", "/search", "/search?q=", "https://example.com/c/A", "/other"]
)
def test_rejects_other_urls(url):
    assert parse(url) is None


def test_resolve_checks_against_data(catalog):
    good = "/c/子育て・教育/健診・予防接種/予防接種#svc=定期予防接種"
    assert resolve(catalog, good).url == category_url(
        ("子育て・教育", "健診・予防接種", "予防接種"), ["定期予防接種"]
    )
    assert resolve(catalog, "/c/子育て・教育/健診・予防接種/予防接種#svc=架空の窓口") is None
    assert resolve(catalog, "/c/子育て・教育/存在しない") is None
    assert resolve(catalog, "/search?q=予防接種") == SearchLocation("予防接種")
    assert resolve(catalog, "/search?q=該当なしの語") is None


# --- cli ---


def test_cli_validate(tmp_path, capsys):
    assert main(["validate", str(SMALL)]) == 0
    assert "OK: カテゴリ 18 件、サービス 14 件" in capsys.readouterr().out

    shutil.copytree(SMALL, tmp_path / "broken")
    with (tmp_path / "broken" / "services.csv").open("a", encoding="utf-8") as f:
        f.write("子育て・教育,,,親に所属,,,,\n")
    assert main(["validate", str(tmp_path / "broken")]) == 1
    assert "services.csv:16: 末端ではないカテゴリです: 子育て・教育" in capsys.readouterr().err
