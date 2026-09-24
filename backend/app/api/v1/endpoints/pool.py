"""机构推荐池 (recommend pool) — sina 上调/下调/首次评级名单 (Phase 1 gap fill).

Read-only; rows are ingested by the ``recommend_pool`` feed. Shaped like the
signals endpoints so the frontend can share the same page skeleton.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import clamp_page, envelope, paged, parse_date
from app.core.db import get_db
from app.services import recommend_pool as pool_svc

router = APIRouter(prefix="/api/pool", tags=["pool"])


@router.get("/list")
def pool_list(
    kind: str | None = Query(default=None, description="upgrade|downgrade|first"),
    industry: str | None = None,
    days: int = Query(default=30, ge=1, le=365),
    date_: str | None = Query(default=None, alias="date", description="exact session YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    page, size = clamp_page(page, size)
    rows, total, ref = pool_svc.list_pool(
        db, kind=kind, industry=industry, days=days,
        date_=parse_date(date_), page=page, size=size,
    )
    return paged(rows, total, page, size, ref=ref.isoformat() if ref else None, days=days)


@router.get("/summary")
def pool_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(pool_svc.summary(db, days))
