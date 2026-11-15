"""ホスト型エージェントのサーバー (localhost:8088 の `/responses`)。

`AGENT_MODE=stub` でスタブ、`AGENT_MODE=foundry` (既定) で Foundry のプロンプト エージェントを使う。
"""

import logging
from typing import Any

from agent_framework_foundry_hosting import ResponsesHostServer

from consultation.workflow import build_workflow, checkpoint_store_provider, parse_response


def create_server(**kwargs: Any) -> ResponsesHostServer:
    return ResponsesHostServer(
        workflow=build_workflow,
        parse_response=parse_response,
        checkpoint_store_provider=checkpoint_store_provider(),
        **kwargs,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    create_server().run()


if __name__ == "__main__":
    main()
