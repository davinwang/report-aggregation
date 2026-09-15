"""Caching layer — pure in-process, zero external dependencies.

- ``cachetools.TTLCache`` for fast in-memory access with a generous safety TTL.
- Pickle file (``data/cache.pkl``) for persistence across restarts.
- Thread-safe via ``threading.Lock``; atomic writes via temp-file + rename.

Used for hot, expensive-to-compute read endpoints (全市场速览 matrix, 板块联动 beta).
Data correctness still comes from the DB: entries remember the SQLite header's
change counter, which moves on every committed write, so any write — scheduler
run, API trigger or an out-of-process CLI backfill — invalidates the cache, and a
page never serves results computed before the latest data landed. The counter is
file *content*, immune to the mtime jitter Docker Desktop bind mounts can show for
the same file; when the stamp stays unreadable after retries the entry is
recomputed rather than served unvalidated, so a page never displays data whose
freshness could not be confirmed. ``cache_clear``
additionally wipes everything at the end of each in-process ingestion run.
"""
from __future__ import annotations

import os
import pickle
import struct
import tempfile
import threading
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from cachetools import TTLCache

from app.core.config import BACKEND_DIR
from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE_FILE = BACKEND_DIR.parent / "data" / "cache.pkl"
_LOCK = threading.Lock()
#: Safety bound only — stale entries are normally dropped by the DB change-counter
#: check below (daily data changes a few times per day, not every minute).
_TTL_SECONDS = 30 * 60
#: Byte offset of the SQLite header's file-change counter (uint32, big-endian).
#: It increments on every committed write transaction — SQLite's own mechanism
#: for cross-process change detection; unlike mtime it is file content, not
#: filesystem metadata, so bind-mount timestamp jitter cannot affect it.
_DB_COUNTER_OFFSET = 24
_LOCAL: TTLCache = TTLCache(maxsize=512, ttl=_TTL_SECONDS)
#: Entry shape: (change counter at compute time, cached value).
_Entry = tuple[int, Any]


_STAMP_WARN_TS = 0.0
_STAMP_ATTEMPTS = 3
_STAMP_RETRY_DELAY = 0.1


def _db_stamp() -> int | None:
    """SQLite header's file-change counter — moves on every committed write.

    ``None`` means the stamp stays unreadable after retries (read hiccups over
    the Windows Docker bind mount are common right after container start):
    callers treat it as "cannot validate" and recompute — a value whose
    freshness cannot be checked is never served.
    """
    global _STAMP_WARN_TS
    for attempt in range(_STAMP_ATTEMPTS):
        if attempt:
            time.sleep(_STAMP_RETRY_DELAY)  # ride out the post-start flaky window
        try:
            from app.core.db import engine  # local: keep cache imports lightweight

            db_path = engine.url.database
            if not db_path:
                return None
            with open(db_path, "rb") as fh:
                fh.seek(_DB_COUNTER_OFFSET)
                raw = fh.read(4)
            if len(raw) == 4:
                return struct.unpack(">I", raw)[0]
        except Exception:  # noqa: BLE001 - stamp failures must not break reads
            continue
    now = time.monotonic()
    if now - _STAMP_WARN_TS > 60:  # rate-limit: a broken mount must not spam logs
        _STAMP_WARN_TS = now
        logger.warning("SQLite change counter unreadable; entries will be recomputed")
    return None


def _load() -> None:
    """Load persisted cache from pickle file (if present) into the in-memory TTLCache."""
    if not _CACHE_FILE.exists():
        return
    try:
        with _CACHE_FILE.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], (int, float)):
                    _LOCAL[k] = v  # (stamp, value) only; pre-counter float stamps drop on first check
        logger.info("Loaded %d cache entries from %s", len(_LOCAL), _CACHE_FILE)
    except Exception as exc:
        logger.warning("Failed to load cache from %s: %s", _CACHE_FILE, exc)


def _save() -> None:
    """Persist the current in-memory cache to pickle file (atomic write)."""
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=_CACHE_FILE.parent, suffix=".pkl.tmp")
        with os.fdopen(fd, "wb") as f:
            pickle.dump(dict(_LOCAL), f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, _CACHE_FILE)
    except Exception as exc:
        logger.warning("Failed to save cache to %s: %s", _CACHE_FILE, exc)
        try:
            os.unlink(tmp)
        except OSError:
            pass


# Load persisted cache on module import.
_load()


def cache_get(key: str) -> Any | None:
    """Return the cached value, or None when absent/stale/unvalidatable.

    The stamp is read before taking the lock so stamp retries cannot serialize
    readers. An unreadable stamp counts as a miss: the caller recomputes.
    """
    current = _db_stamp()
    with _LOCK:
        entry: _Entry | None = _LOCAL.get(key)
        if entry is None:
            return None
        stamp, value = entry
        if current is None:
            return None  # cannot validate freshness; recompute instead of serving
        if current != stamp:
            _LOCAL.pop(key, None)  # data landed since this payload was computed
            return None
        return value


def cache_set(key: str, value: Any, ttl: int = _TTL_SECONDS) -> None:
    """Store ``value`` for ``key``, stamped with the current change counter.

    ``ttl`` is accepted for API compatibility; the effective lifetime is the
    cache-level TTL, and staleness is primarily governed by the counter check.
    The store is skipped when the stamp stays unreadable — an unstampable entry
    could never be validated later.
    """
    stamp = _db_stamp()
    if stamp is None:
        return
    with _LOCK:
        _LOCAL[key] = (stamp, value)
        _save()


def cache_clear(prefix: str | None = None) -> None:
    with _LOCK:
        if prefix is None:
            _LOCAL.clear()
            if _CACHE_FILE.exists():
                try:
                    _CACHE_FILE.unlink()
                except OSError:
                    pass
        else:
            for k in [k for k in list(_LOCAL.keys()) if str(k).startswith(prefix)]:
                _LOCAL.pop(k, None)
            _save()


def cached(ttl: int = _TTL_SECONDS, key_func: Callable[..., str] | None = None) -> Callable:
    """Decorator caching a function result by its args (or a custom key_func)."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if key_func is not None:
                key = key_func(*args, **kwargs)
            else:
                key = f"{fn.__module__}.{fn.__qualname__}:{args}:{sorted(kwargs.items())}"
            hit = cache_get(key)
            if hit is not None:
                return hit
            result = fn(*args, **kwargs)
            if result is not None:
                cache_set(key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
