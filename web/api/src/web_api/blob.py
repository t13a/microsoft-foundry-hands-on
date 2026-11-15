"""Blob Storage からカタログの CSV を取ってくる (基本設計書 7.1)。"""

import tempfile
from pathlib import Path

from catalog.loader import CATEGORIES_FILE, SERVICES_FILE


def download_catalog(container_url: str) -> Path:
    """コンテナーの CSV を一時フォルダーに落とし、そのフォルダーを返す。認証はマネージド ID。"""
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import ContainerClient

    directory = Path(tempfile.mkdtemp(prefix="catalog-"))
    with ContainerClient.from_container_url(container_url, DefaultAzureCredential()) as container:
        for name in (CATEGORIES_FILE, SERVICES_FILE):
            (directory / name).write_bytes(container.download_blob(name).readall())
    return directory
