"""ローカルで BFF を起動する: uv run python -m web_api (localhost:8000)。"""

import os

import uvicorn

from web_api.app import create_app

if __name__ == "__main__":
    uvicorn.run(
        create_app(),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
