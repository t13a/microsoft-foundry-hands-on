"""カタログのデータ: カテゴリの木とサービス。"""

from dataclasses import dataclass, field

type CategoryPath = tuple[str, ...]


@dataclass(frozen=True)
class Service:
    category_path: CategoryPath
    name: str
    description: str
    address: str
    phone: str
    url: str


@dataclass
class Category:
    path: CategoryPath
    description: str
    children: list["Category"] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path[-1]

    @property
    def is_leaf(self) -> bool:
        return not self.children


@dataclass
class Catalog:
    """CSV から読み込んだ全データ。表示順は CSV の行の順。"""

    top: list[Category]
    categories: dict[CategoryPath, Category]
    services: list[Service]

    def category(self, path: CategoryPath) -> Category | None:
        return self.categories.get(tuple(path))

    def service(self, path: CategoryPath, name: str) -> Service | None:
        category = self.category(path)
        if category is None:
            return None
        return next((s for s in category.services if s.name == name), None)
