"""ホスト型エージェントの入口 (コード デプロイの entryPoint)。

デプロイ用に組んだフォルダー (`scripts/stage-agent.sh`) では、パッケージ、文言、データが
このファイルの隣にある。
"""

import os
from pathlib import Path

here = Path(__file__).resolve().parent
if (here / "content").is_dir():
    os.environ.setdefault("CONSULTATION_CONTENT_DIR", str(here / "content"))
if (here / "data").is_dir():
    os.environ.setdefault("CATALOG_DIR", str(here / "data"))

from consultation.server import main  # noqa: E402

if __name__ == "__main__":
    main()
