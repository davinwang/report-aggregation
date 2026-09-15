"""Central logging setup.

Provides a single ``configure_logging`` entry point and a ``get_logger`` helper so
every module logs consistently (level from ENV, UTC timestamps, module names).
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def _stdout_utf8():
    """Return stdout forced to UTF-8.

    Windows consoles default to GBK (cp936) so log glyphs such as ``▶`` raise
    UnicodeEncodeError inside the handler; forcing UTF-8 (with replacement) keeps
    host-side CLI runs (``python -m app.ingestion.pipeline``) from crashing.
    """
    stream = sys.stdout
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass
    return stream


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(_stdout_utf8())
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Quiet noisy third-party loggers.
    for noisy in ("apscheduler.executors.default", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_logging()
    return logging.getLogger(name)
