"""Lazy AkShare client.

AkShare is imported lazily so that:
- the API server and frontend dev can run even if akshare isn't installed yet;
- tests can monkeypatch ``get_ak()`` with a fake module returning recorded frames;
- a broken/absent akshare surfaces as a clear, single error rather than an import crash.
"""
from __future__ import annotations

import threading
from types import ModuleType
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_ak: Optional[ModuleType] = None
_import_error: Optional[str] = None


class AkShareUnavailable(RuntimeError):
    """Raised when akshare is not installed or failed to import."""


def get_ak() -> ModuleType:
    """Return the akshare module, importing it on first use."""
    global _ak, _import_error
    if _ak is not None:
        return _ak
    with _lock:
        if _ak is not None:
            return _ak
        try:
            import akshare as ak  # noqa: PLC0415

            _ak = ak
            logger.info("akshare imported (version=%s)", getattr(ak, "__version__", "unknown"))
            return _ak
        except Exception as exc:  # pragma: no cover - depends on environment
            _import_error = str(exc)
            logger.error("Failed to import akshare: %s", exc)
            raise AkShareUnavailable(
                "akshare is not available. Install backend deps: pip install -r requirements.txt"
            ) from exc


def akshare_version() -> Optional[str]:
    try:
        return getattr(get_ak(), "__version__", None)
    except AkShareUnavailable:
        return None


def set_fake_ak(fake: Optional[ModuleType]) -> None:
    """Test hook: inject a fake akshare module (or None to reset)."""
    global _ak, _import_error
    with _lock:
        _ak = fake
        _import_error = None
