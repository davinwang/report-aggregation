"""Lazy AkShare client.

AkShare is imported lazily so that:
- the API server and frontend dev can run even if akshare isn't installed yet;
- tests can monkeypatch ``get_ak()`` with a fake module returning recorded frames;
- a broken/absent akshare surfaces as a clear, single error rather than an import crash.
"""
from __future__ import annotations

import threading
from types import ModuleType

from app.core.logging import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_ak: ModuleType | None = None
_import_error: str | None = None


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


def akshare_version() -> str | None:
    """Installed akshare version without importing the (heavy) package.

    Importing akshare costs seconds, and /health/deep is a read endpoint — probing
    must never stall a page load. The dist metadata gives the same answer; when the
    module has already been imported (by ingestion) its ``__version__`` is used.
    """
    if _ak is not None:
        return getattr(_ak, "__version__", None)
    try:
        from importlib.metadata import version

        return version("akshare")
    except Exception:  # noqa: BLE001 - not installed / broken metadata
        return None


def set_fake_ak(fake: ModuleType | None) -> None:
    """Test hook: inject a fake akshare module (or None to reset)."""
    global _ak, _import_error
    with _lock:
        _ak = fake
        _import_error = None
