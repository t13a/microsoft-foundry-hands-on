import logging
from pathlib import Path

import pytest

FIXTURE_DATA = Path(__file__).resolve().parents[2] / "packages/catalog/tests/fixtures/small"


@pytest.fixture(autouse=True)
def environment(monkeypatch, tmp_path):
    # data/ はまだないので、カタログのテスト用データを使う。
    monkeypatch.setenv("CATALOG_DIR", str(FIXTURE_DATA))
    monkeypatch.setenv("AGENT_MODE", "stub")
    monkeypatch.setenv("AGENTSERVER_STATE_ROOT", str(tmp_path / "agentserver"))
    monkeypatch.delenv("STUB_SCENARIO", raising=False)
    monkeypatch.delenv("CONSULTATION_CONTENT_DIR", raising=False)
    # ホストの OpenTelemetry のログ出力 (コンソール) を抑える。
    logging.getLogger("azure.ai.agentserver").setLevel(logging.WARNING)
