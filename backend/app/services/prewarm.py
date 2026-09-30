"""Prewarm the hot read caches so first page visits never pay a cold computation.

The heavy read endpoints (全市场速览 ``quant.matrix``, 技术信号矩阵 ``quant.signal``,
板块联动 ``linkage.*``) cache their computed payloads; without a warm cache the first
visitor after a container restart / ingestion run pays the full computation over the
bind-mounted SQLite file. Warming the default parameter sets at boot and after each
ingestion keeps first visits fast — data still comes from the local DB, the cache only
mirrors it.
"""
from __future__ import annotations

from collections.abc import Callable
from functools import partial

from app.api.v1.endpoints import linkage as linkage_ep
from app.api.v1.endpoints import quant as quant_ep
from app.core.cache import cache_get
from app.core.db import session_scope
from app.core.logging import get_logger
from app.services import signal_matrix as signal_svc

logger = get_logger(__name__)

#: Parameter sets the UI loads first (see the 全市场速览 / 板块联动 pages), ordered
#: by usage: matrix Top60 is the default view, then the linkage panes.
_MATRIX_KEYS: tuple[tuple[str, int], ...] = (
    ("index+active", 60),
    ("index+active", 120),
    ("index+active", 30),
)
#: 技术信号矩阵 — the 技术指标 page's default tab. Scoped per universe because each one
#: is a separate compute over a separate set of bars.
_SIGNAL_KEYS: tuple[tuple[str, str, int], ...] = (
    ("index", "daily", 60),
    ("etf", "daily", 60),
    ("bond", "daily", 50),
    ("stock", "daily", 60),
)
_BETA_KEYS: tuple[tuple[str, int, int], ...] = (
    ("sh000300", 120, 100),
)
_LINKAGE_MATRIX_WINDOWS: tuple[int, ...] = (120,)


def prewarm_hot_caches() -> None:
    """Best-effort precompute of the hot payloads; never raises into the caller.

    Each key is isolated: a failing key is logged and skipped so the rest still
    warm. Every compute is re-checked against the cache, and computes that fail
    to stick (DB stamp unreadable right after container start) are retried once,
    so the log reports honest numbers.
    """
    warmed = skipped = failed = 0
    try:
        with session_scope() as db:
            jobs: list[tuple[str, Callable[[], object]]] = []
            for scope, limit in _MATRIX_KEYS:
                jobs.append((
                    f"quant.matrix:{scope}:{limit}",
                    partial(quant_ep.matrix, freq="daily", limit=limit, scope=scope, db=db),
                ))
            for scope, freq, limit in _SIGNAL_KEYS:
                jobs.append((
                    signal_svc.cache_key_for(scope=scope, freq=freq, limit=limit),
                    partial(quant_ep.signal_matrix, scope=scope, freq=freq, limit=limit,
                            columns=None, liquidity_floor=signal_svc.LIQUIDITY_FLOOR, db=db),
                ))
            for benchmark, window, limit in _BETA_KEYS:
                jobs.append((
                    f"linkage.beta:{benchmark}:{window}:{limit}",
                    partial(linkage_ep.beta, window=window, benchmark=benchmark, limit=limit, db=db),
                ))
            for window in _LINKAGE_MATRIX_WINDOWS:
                jobs.append((
                    f"linkage.matrix:{window}",
                    partial(linkage_ep.matrix, window=window, db=db),
                ))

            pending = jobs
            for attempt in (1, 2):
                if not pending:
                    break
                retry: list[tuple[str, Callable[[], object]]] = []
                for key, compute in pending:
                    if attempt == 1 and cache_get(key) is not None:
                        skipped += 1
                        continue
                    try:
                        compute()
                    except Exception:  # noqa: BLE001 - one bad key must not stop the rest
                        failed += 1
                        logger.exception("Prewarm failed for %s", key)
                        continue
                    if cache_get(key) is None:
                        retry.append((key, compute))
                    else:
                        warmed += 1
                pending = retry
            for key, _compute in pending:
                failed += 1
                logger.warning("Prewarm of %s did not stick (DB stamp unreadable?)", key)
    except Exception:  # noqa: BLE001 - warming is opportunistic, never fatal
        logger.exception("Hot cache prewarm aborted")
        return
    logger.info("Hot read caches prewarmed (%d warmed, %d already warm, %d failed)",
                warmed, skipped, failed)
