"""SSE stream endpoint (live-refresh channel via SSE).

On connect the client receives a ``hello`` event (parity with "SSE 已就绪"), a replay of
recent events, then a live feed of ingestion progress + freshness updates. A comment
keep-alive is sent every 15s to defeat idle proxies.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.sse import bus

router = APIRouter(tags=["stream"])


@router.get("/api/stream")
async def stream(request: Request) -> StreamingResponse:
    q = bus.subscribe()

    async def event_gen():
        try:
            yield bus.format_sse({
                "event": "hello",
                "data": {"status": "SSE 已就绪", "subscribers": bus.subscriber_count()},
            })
            for m in bus.recent(10):
                yield bus.format_sse(m)
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield bus.format_sse(msg)
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/api/stream/recent")
def recent(n: int = 50) -> dict:
    return {"data": bus.recent(n), "meta": {"subscribers": bus.subscriber_count()}}
