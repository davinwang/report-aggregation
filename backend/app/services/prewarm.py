"""Prewarm the hot read caches so first page visits never pay a cold computation.

The heavy read endpoints (全市场速览 ``quant.matrix``, 板块联动 ``linkage.*``) cache
their computed payloads; without a warm cache the first visitor after a container
restart / ingestion run pays the full computation over the bind-mounted SQLite
file. Warming the default parameter sets at boot and after each ingestion keeps
first visits fast — data still comes from the local DB, the cache only mirrors it.
"""
from __future__ import annotations

from app.api.v1.endpoints import linkage as linkage_ep
from app.api.v1.endpoints import quant as quant_ep
from app.core.cache import cache_get
from app.core.db import session_scope
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Parameter sets the UI loads first (see the 全市场速览 / 板块联动 pages), ordered
#: by usage: matrix Top60 is the default view, then the linkage panes.
_MATRIX_KEYS: tuple[tuple[str, int], ...] = (
    ("index+active", 60),
    ("index+active", 120),
    ("index+active", 30),
)
_BETA_KEYS: tuple[tuple[str, int, int], ...] = (
    ("sh000300", 120, 100),
)
_LINKAGE_MATRIX_WINDOWS: tuple[int, ...] = (120,)


def prewarm_hot_caches() -> None:
    """Best-effort precompute of the hot payloads; never raises into the caller."""
    try:
        with session_scope() as db:
            for scope, limit in _MATRIX_KEYS:
                if cache_get(f"quant.matrix:{scope}:{limit}") is None:
                    quant_ep.matrix(freq="daily", limit=limit, scope=scope, db=db)
            for benchmark, window, limit in _BETA_KEYS:
                if cache_get(f"linkage.beta:{benchmark}:{window}:{limit}") is None:
                    linkage_ep.beta(window=window, benchmark=benchmark, limit=limit, db=db)
            for window in _LINKAGE_MATRIX_WINDOWS:
                if cache_get(f"linkage.matrix:{window}") is None:
                    linkage_ep.matrix(window=window, db=db)
        logger.info("Hot read caches prewarmed (%d matrix, %d beta, %d linkage)",
                    len(_MATRIX_KEYS), len(_BETA_KEYS), len(_LINKAGE_MATRIX_WINDOWS))
    except Exception:  # noqa: BLE001 - warming is opportunistic, never fatal
        logger.exception("Hot cache prewarm failed")
