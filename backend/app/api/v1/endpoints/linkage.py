"""板块/指数联动 (linkage) — index correlation matrix + stock Beta (Phase 2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.cache import cache_get, cache_set
from app.core.db import get_db
from app.services import linkage as linkage_svc

router = APIRouter(prefix="/api/linkage", tags=["linkage"])


@router.get("/matrix")
def matrix(
    window: int = Query(default=120, ge=20, le=500, description="rolling window in trading days"),
    db: Session = Depends(get_db),
) -> dict:
    """指数相关性矩阵 (Pearson of daily returns) + strongest pairs."""
    cache_key = f"linkage.matrix:{window}"
    cached = cache_get(cache_key)
    if cached is not None:
        return envelope(cached)
    payload = linkage_svc.correlation_matrix(db, window=window)
    cache_set(cache_key, payload)
    return envelope(payload)


@router.get("/beta")
def beta(
    window: int = Query(default=120, ge=20, le=500),
    benchmark: str = Query(default="sh000300"),
    limit: int = Query(default=100, ge=5, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """个股 Beta/ρ² vs 沪深300 (from 前复权 close history)."""
    cache_key = f"linkage.beta:{benchmark}:{window}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return envelope(cached)
    payload = linkage_svc.beta_table(db, benchmark=benchmark, window=window, limit=limit)
    cache_set(cache_key, payload)
    return envelope(payload)
