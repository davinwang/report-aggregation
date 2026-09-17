"""Static-token auth for the MCP endpoint (pure ASGI middleware).

When ``settings.mcp_token`` is set, every HTTP request must carry
``Authorization: Bearer <token>``; when it is empty the middleware passes
through (LAN/dev posture, mirroring ``AUTH_ENABLED=false``). The token is read
per-request so tests can monkeypatch settings. 401s answer as JSON.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from app.core.config import settings


class TokenAuthMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http" or not settings.mcp_token:
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        auth = headers.get(b"authorization", b"").decode("latin-1")
        scheme, _, token = auth.partition(" ")
        if scheme.lower() == "bearer" and token == settings.mcp_token:
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {"error": "unauthorized", "detail": "missing or invalid MCP token"}
        ).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        })
        await send({"type": "http.response.body", "body": body})
