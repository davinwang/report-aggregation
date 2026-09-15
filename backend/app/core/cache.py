"""Caching layer — pure in-process, zero external dependencies.

- ``cachetools.TTLCache`` for fast in-memory access with TTL.
- Pickle file (``data/cache.pkl``) for persistence across restarts.
- Thread-safe via ``threading.Lock``; atomic writes via temp-file + rename.

Used for hot, expensive-to-compute read endpoints (全市场速览 matrix, 板块联动 beta).
Data correctness still comes from the DB; the cache only short-circuits repeated
aggregation and is cleared when an ingestion run finishes (``BaseAdapter.run``),
so a page never serves pre-ingestion results beyond that boundary.
"""
from __future__ import annotations

import os
import pickle
import tempfile
import threading
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any

from cachetools import TTLCache

from app.core.config import BACKEND_DIR
from app.core.logging import get_logger

logger = get_logger(__name__)

_CACHE_FILE = BACKEND_DIR.parent / "data" / "cache.pkl"
_LOCK = threading.Lock()
_LOCAL: TTLCache = TTLCache(maxsize=512, ttl=60)


def _load() -> None:
    """Load persisted cache from pickle file (if present) into the in-memory TTLCache."""
    if not _CACHE_FILE.exists():
        return
    try:
        with _CACHE_FILE.open("rb") as f:
            data = pickle.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                _LOCAL[k] = v
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
    with _LOCK:
        return _LOCAL.get(key)


def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    with _LOCK:
        _LOCAL[key] = value
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


def cached(ttl: int = 60, key_func: Callable[..., str] | None = None) -> Callable:
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
