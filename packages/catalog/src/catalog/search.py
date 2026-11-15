"""キーワード検索 (基本設計書 7.2)。"""

import unicodedata

from catalog.model import Catalog, Service


def normalize(text: str) -> str:
    """全角・半角と大文字・小文字の違いを吸収する (F-SITE-05)。"""
    return unicodedata.normalize("NFKC", text).casefold()


def terms(query: str) -> list[str]:
    """空白で区切った検索語。全角の空白も区切りとして扱う。"""
    return normalize(query).split()


def search(catalog: Catalog, query: str) -> list[Service]:
    """すべての語を含むサービスを、CSV の行の順で返す。語がなければ空。"""
    words = terms(query)
    if not words:
        return []
    return [s for s in catalog.services if all(w in _haystack(s) for w in words)]


def _haystack(service: Service) -> str:
    fields = (
        service.name,
        service.description,
        service.address,
        service.phone,
        service.url,
        *service.category_path,
    )
    return normalize("\n".join(fields))
