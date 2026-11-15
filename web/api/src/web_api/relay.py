"""Responses の中継 (基本設計書 6.1、6.2、6.3)。

SPA の要求を、送信先を固定してホスト型エージェントの Responses の受け口へ送り、SSE をそのまま返す。
プロトコルは変換せず、状態も持たない (送信頻度の数だけはメモリに持つ)。
"""

import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask

# Only these fields reach the agent, so a request cannot pick another agent, model or tools.
ALLOWED_FIELDS = ("input", "previous_response_id", "store", "agent_session_id")
TOKEN_SCOPE = "https://ai.azure.com/.default"


@dataclass
class RelaySettings:
    """設定は環境変数で渡す。

    - AGENT_RESPONSES_URL: 送信先 (既定はローカルのホスト型エージェント)
    - AGENT_AUTH=managed_identity: マネージド ID のトークンを付ける (Azure 上)
    - AGENT_PLATFORM_SESSIONS=1: セッション ID を基盤に決めさせる (最初の要求から省く)
    - RATE_LIMIT_PER_MINUTE: IP アドレスごとの送信の上限
    """

    url: str = "http://localhost:8088/responses"
    managed_identity: bool = False
    platform_sessions: bool = False
    rate_limit_per_minute: int = 20

    @classmethod
    def from_env(cls) -> "RelaySettings":
        return cls(
            url=os.environ.get("AGENT_RESPONSES_URL", cls.url),
            managed_identity=os.environ.get("AGENT_AUTH") == "managed_identity",
            platform_sessions=os.environ.get("AGENT_PLATFORM_SESSIONS") == "1",
            rate_limit_per_minute=int(os.environ.get("RATE_LIMIT_PER_MINUTE", "20")),
        )


@dataclass
class RateLimiter:
    """1 分あたりの送信回数を IP アドレスごとに数える。レプリカは最大 1 なのでメモリで足りる。"""

    per_minute: int
    clock: object = time.monotonic
    _hits: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(deque))

    def allow(self, key: str) -> bool:
        now = self.clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            return False
        hits.append(now)
        return True


def client_ip(request: Request) -> str:
    # Container Apps' ingress puts the caller first in X-Forwarded-For.
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "")


def create_router(settings: RelaySettings, client: httpx.AsyncClient | None = None) -> APIRouter:
    router = APIRouter()
    limiter = RateLimiter(settings.rate_limit_per_minute)
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(10, read=300))
    credential = None
    if settings.managed_identity:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()

    @router.post("/api/responses")
    async def responses(request: Request) -> Response:
        if not limiter.allow(client_ip(request)):
            raise HTTPException(429, "送信が多すぎます。少し待ってからもう一度お試しください。")
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400)
        payload = {k: body[k] for k in ALLOWED_FIELDS if body.get(k) is not None}
        payload["stream"] = True
        if settings.platform_sessions and "previous_response_id" not in payload:
            # On Foundry the first response returns the session to reuse.
            payload.pop("agent_session_id", None)

        headers = {"content-type": "application/json"}
        if credential is not None:
            token = await run_in_threadpool(credential.get_token, TOKEN_SCOPE)
            headers["authorization"] = f"Bearer {token.token}"

        upstream = await http.send(
            http.build_request("POST", settings.url, json=payload, headers=headers), stream=True
        )
        if upstream.is_error:
            content = await upstream.aread()
            await upstream.aclose()
            return Response(
                content,
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type"),
            )
        return StreamingResponse(
            upstream.aiter_raw(),
            media_type=upstream.headers.get("content-type", "text/event-stream"),
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
            background=BackgroundTask(upstream.aclose),
        )

    return router
