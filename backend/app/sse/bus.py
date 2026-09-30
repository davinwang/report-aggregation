"""In-process SSE event bus.

Ingestion runs in worker threads (APScheduler) while SSE subscribers live in the
asyncio loop, so ``publish`` is thread-safe: it appends to a bounded recent-events
ring buffer and fans out to subscriber queues via ``loop.call_soon_threadsafe``.
"""
from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

_lock = threading.Lock()
_subscribers: set[asyncio.Queue] = set()
_recent: deque[dict] = deque(maxlen=200)
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop | None) -> None:
    """Called on app startup/shutdown to bind the running event loop."""
    global _loop
    _loop = loop


def _stamp(event: str, data: Any) -> dict:
    return {
        "event": event,
        "ts": datetime.now(UTC).isoformat(),
        "data": data,
    }


def publish(event: str, data: Any = None) -> None:
    msg = _stamp(event, data)
    with _lock:
        _recent.append(msg)
        subs = list(_subscribers)
    loop = _loop
    if loop is None or loop.is_closed():
        return
    for q in subs:
        try:
            loop.call_soon_threadsafe(_safe_put, q, msg)
        except RuntimeError:
            # loop shut down between snapshot and call
            break


def _safe_put(q: asyncio.Queue, msg: dict) -> None:
    try:
        q.put_nowait(msg)
    except asyncio.QueueFull:
        # Drop oldest to make room (slow consumer).
        try:
            q.get_nowait()
            q.put_nowait(msg)
        except Exception:  # noqa: BLE001
            pass


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    with _lock:
        _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    with _lock:
        _subscribers.discard(q)


def recent(n: int = 50) -> list[dict]:
    with _lock:
        return list(_recent)[-n:]


def subscriber_count() -> int:
    with _lock:
        return len(_subscribers)


def format_sse(msg: dict) -> str:
    """Serialize a message dict to an SSE frame."""
    return f"event: {msg['event']}\ndata: {json.dumps(msg['data'], ensure_ascii=False, default=str)}\n\n"
