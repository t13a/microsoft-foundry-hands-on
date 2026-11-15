"""CSV の読み込みと検証 (要求仕様書 6.1、6.2)。"""

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from catalog.model import Catalog, Category, CategoryPath, Service

CATEGORIES_FILE = "categories.csv"
SERVICES_FILE = "services.csv"

LEVELS = ("階層1", "階層2", "階層3")
CATEGORY_COLUMNS = (*LEVELS, "説明")
SERVICE_COLUMNS = (*LEVELS, "名称", "説明", "住所", "電話番号", "ホームページURL")


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    reason: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.reason}"


class InvalidCatalogError(Exception):
    def __init__(self, violations: list[Violation]) -> None:
        super().__init__("\n".join(str(v) for v in violations))
        self.violations = violations


def load(directory: Path | str) -> Catalog:
    """CSV を読み込む。制約に違反していたら、違反をすべて載せて InvalidCatalogError を投げる。"""
    catalog, violations = _load(Path(directory))
    if violations:
        raise InvalidCatalogError(violations)
    return catalog


def validate(directory: Path | str) -> list[Violation]:
    """CSV を検証し、違反の一覧を返す (違反がなければ空)。"""
    return _load(Path(directory))[1]


def _load(directory: Path) -> tuple[Catalog, list[Violation]]:
    violations: list[Violation] = []
    categories: dict[CategoryPath, Category] = {}
    top: list[Category] = []
    services: list[Service] = []

    category_rows = list(_read(directory / CATEGORIES_FILE, CATEGORY_COLUMNS, violations))
    for line, row in category_rows:
        path, reason = _path(row)
        if reason:
            violations.append(Violation(CATEGORIES_FILE, line, reason))
            continue
        if path in categories:
            # F-DAT-11
            violations.append(
                Violation(CATEGORIES_FILE, line, f"カテゴリが重複しています: {_show(path)}")
            )
            continue
        categories[path] = Category(path, row["説明"])

    # Link parents after reading every row: a parent may appear after its children.
    for line, row in category_rows:
        path, reason = _path(row)
        if reason or path not in categories:
            continue
        category = categories[path]
        if len(path) == 1:
            if category not in top:
                top.append(category)
            continue
        parent = categories.get(path[:-1])
        if parent is None:
            # F-DAT-12
            violations.append(
                Violation(CATEGORIES_FILE, line, f"親カテゴリがありません: {_show(path[:-1])}")
            )
        elif category not in parent.children:
            parent.children.append(category)

    for line, row in _read(directory / SERVICES_FILE, SERVICE_COLUMNS, violations):
        path, reason = _path(row)
        if reason:
            violations.append(Violation(SERVICES_FILE, line, reason))
            continue
        name = row["名称"].strip()
        if not name:
            violations.append(Violation(SERVICES_FILE, line, "名称が空です"))
            continue
        category = categories.get(path)
        if category is None:
            # F-DAT-13
            violations.append(
                Violation(SERVICES_FILE, line, f"カテゴリがありません: {_show(path)}")
            )
            continue
        if not category.is_leaf:
            # F-DAT-13
            violations.append(
                Violation(SERVICES_FILE, line, f"末端ではないカテゴリです: {_show(path)}")
            )
            continue
        if any(s.name == name for s in category.services):
            # F-DAT-14
            violations.append(
                Violation(SERVICES_FILE, line, f"同じカテゴリに同じ名称があります: {name}")
            )
            continue
        service = Service(
            category_path=path,
            name=name,
            description=row["説明"],
            address=row["住所"],
            phone=row["電話番号"],
            url=row["ホームページURL"],
        )
        category.services.append(service)
        services.append(service)

    return Catalog(top=top, categories=categories, services=services), violations


def _read(
    path: Path, columns: tuple[str, ...], violations: list[Violation]
) -> Iterator[tuple[int, dict[str, str]]]:
    """行番号 (レコードが始まる物理行) と、列名をキーにした行を返す。"""
    if not path.exists():
        violations.append(Violation(path.name, 0, "ファイルがありません"))
        return
    # utf-8-sig accepts the BOM that Excel needs (F-DAT-02).
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or tuple(h.strip() for h in header) != columns:
            violations.append(
                Violation(path.name, 1, f"列が違います (期待する列: {', '.join(columns)})")
            )
            return
        start = reader.line_num + 1
        for record in reader:
            line, start = start, reader.line_num + 1
            if not any(cell.strip() for cell in record):
                continue
            if len(record) != len(columns):
                violations.append(
                    Violation(path.name, line, f"列の数が違います ({len(record)} 列)")
                )
                continue
            yield line, dict(zip(columns, record, strict=True))


def _path(row: dict[str, str]) -> tuple[CategoryPath, str | None]:
    names = [row[level].strip() for level in LEVELS]
    while names and not names[-1]:
        names.pop()
    if not names:
        return (), "階層1 が空です"
    if not all(names):
        # F-DAT-10
        return (), "上の階層が空のまま、下の階層が書かれています"
    if any("/" in n for n in names):
        # Category names become URL path segments (F-DAT-20).
        return (), "カテゴリ名に「/」は使えません"
    return tuple(names), None


def _show(path: CategoryPath) -> str:
    return " > ".join(path)
