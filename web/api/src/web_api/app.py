"""BFF: カタログ API、SPA の配信、Basic 認証 (基本設計書 6 章、9.3)。

Responses の中継 (`POST /api/responses`) は段階 S5 で足す。
"""

import base64
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import catalog
from catalog import Catalog, Category, Service
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

REPO_ROOT = Path(__file__).resolve().parents[4]


def create_app(
    catalog_dir: Path | str | None = None,
    static_dir: Path | str | None = None,
    basic_auth: tuple[str, str] | None = None,
) -> FastAPI:
    """BFF のアプリを作る。

    設定は引数か環境変数で渡す (CATALOG_DIR、STATIC_DIR、BASIC_AUTH_USER / BASIC_AUTH_PASSWORD)。
    """
    catalog_dir = Path(catalog_dir or os.environ.get("CATALOG_DIR", REPO_ROOT / "data"))
    static_dir = Path(static_dir or os.environ.get("STATIC_DIR", REPO_ROOT / "web/ui/dist"))
    if basic_auth is None and os.environ.get("BASIC_AUTH_PASSWORD"):
        basic_auth = (os.environ.get("BASIC_AUTH_USER", "demo"), os.environ["BASIC_AUTH_PASSWORD"])

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load once at startup; an invalid CSV stops the app with the violations in the log.
        app.state.catalog = catalog.load(catalog_dir)
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    if basic_auth:
        expected = "Basic " + base64.b64encode(":".join(basic_auth).encode()).decode()

        @app.middleware("http")
        async def require_basic_auth(request: Request, call_next):
            given = request.headers.get("authorization", "")
            if not secrets.compare_digest(given.encode(), expected.encode()):
                return Response(
                    status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="demo-city", charset="UTF-8"'},
                )
            return await call_next(request)

    @app.get("/api/categories")
    def top(request: Request) -> dict:
        data: Catalog = request.app.state.catalog
        return {"categories": [_category_summary(c) for c in data.top]}

    @app.get("/api/categories/{path:path}")
    def category(path: str, request: Request) -> dict:
        data: Catalog = request.app.state.catalog
        found = data.category(tuple(n for n in path.split("/") if n))
        if found is None:
            raise HTTPException(404, "カテゴリがありません")
        return {
            "name": found.name,
            "path": list(found.path),
            "url": catalog.category_url(found.path),
            "description": found.description,
            "breadcrumbs": [
                {"name": found.path[i - 1], "url": catalog.category_url(found.path[:i])}
                for i in range(1, len(found.path))
            ],
            "children": [_category_summary(c) for c in found.children],
            "services": [_service(s) for s in found.services],
        }

    @app.get("/api/search")
    def search(q: str, request: Request) -> dict:
        data: Catalog = request.app.state.catalog
        results = catalog.search(data, q)
        return {"query": q, "count": len(results), "services": [_service(s) for s in results]}

    @app.get("/api/{rest:path}", include_in_schema=False)
    def unknown_api(rest: str) -> None:
        raise HTTPException(404)

    @app.get("/{rest:path}", include_in_schema=False)
    def spa(rest: str) -> FileResponse:
        # Serve built assets as is; every other path is a client-side route.
        file = (static_dir / rest).resolve()
        if rest and file.is_file() and file.is_relative_to(static_dir.resolve()):
            return FileResponse(file)
        index = static_dir / "index.html"
        if not index.is_file():
            raise HTTPException(404, "SPA がビルドされていません")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


def _category_summary(category: Category) -> dict:
    return {
        "name": category.name,
        "url": catalog.category_url(category.path),
        "children": [c.name for c in category.children],
        "serviceCount": len(category.services),
    }


def _service(service: Service) -> dict:
    return {
        "name": service.name,
        "categoryPath": list(service.category_path),
        "description": service.description,
        "address": service.address,
        "phone": service.phone,
        "url": service.url,
        "pageUrl": catalog.category_url(service.category_path, [service.name]),
    }
