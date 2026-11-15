"""画面の URL の生成と解析 (基本設計書 7.3、要求仕様書 6.3)。

生成する URL は各部分をエンコードした決まった形にする。解析はエンコードの有無を問わない
(モデルが URL をデコードしたり、エンコードし直したりして渡すことがあるため)。
"""

from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, unquote, urlsplit

from catalog.model import Catalog, CategoryPath
from catalog.search import search

CATEGORY_PREFIX = "/c/"
SEARCH_PATH = "/search"


@dataclass(frozen=True)
class CategoryLocation:
    path: CategoryPath
    highlights: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        return category_url(self.path, self.highlights)


@dataclass(frozen=True)
class SearchLocation:
    query: str

    @property
    def url(self) -> str:
        return search_url(self.query)


type Location = CategoryLocation | SearchLocation


def category_url(path: CategoryPath, highlights: tuple[str, ...] | list[str] = ()) -> str:
    url = CATEGORY_PREFIX + "/".join(quote(name, safe="") for name in path)
    if highlights:
        url += "#" + "&".join(f"svc={quote(name, safe='')}" for name in highlights)
    return url


def search_url(query: str) -> str:
    return f"{SEARCH_PATH}?q={quote(query, safe='')}"


def parse(url: str) -> Location | None:
    """URL を解析する。カテゴリでも検索結果でもなければ None。データとは照らし合わせない。"""
    parts = urlsplit(url.strip())
    if parts.scheme or parts.netloc:
        return None
    path = unquote(parts.path)
    if path.startswith(CATEGORY_PREFIX):
        names = tuple(n for n in path.removeprefix(CATEGORY_PREFIX).split("/") if n)
        if not names:
            return None
        highlights = tuple(v for k, v in parse_qsl(parts.fragment) if k == "svc" and v)
        return CategoryLocation(names, highlights)
    if path == SEARCH_PATH:
        query = next((v for k, v in parse_qsl(parts.query) if k == "q"), "")
        return SearchLocation(query) if query.strip() else None
    return None


def resolve(catalog: Catalog, url: str) -> Location | None:
    """URL を解析し、実在するデータを指しているときだけ返す。

    カテゴリと強調表示するサービスが存在すること、検索結果が 1 件以上あることを確かめる。
    """
    location = parse(url)
    match location:
        case CategoryLocation(path, highlights):
            category = catalog.category(path)
            if category is None:
                return None
            if any(catalog.service(path, name) is None for name in highlights):
                return None
            return location
        case SearchLocation(query):
            return location if search(catalog, query) else None
    return None
