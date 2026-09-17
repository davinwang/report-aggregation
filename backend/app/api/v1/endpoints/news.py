"""资讯舆情 (news) — whole-market flash news list + summary."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import clamp_page, envelope, paged, parse_date
from app.core.db import get_db
from app.services import news as news_svc

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
def list_news(
    q: Optional[str] = None,
    sentiment: Optional[str] = Query(default=None, description="利好|中性|利空"),
    source: Optional[str] = Query(default=None, description="em|cls"),
    start: Optional[str] = None,
    end: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """Flash news, newest first (keyword/sentiment/source/date filters)."""
    page, size = clamp_page(page, size)
    rows, total = news_svc.list_news(
        db, q=q, sentiment=sentiment, source=source,
        start=parse_date(start), end=parse_date(end), page=page, size=size,
    )
    return paged(rows, total, page, size)


@router.get("/summary")
def summary(
    days: int = Query(default=1, ge=1, le=30),
    db: Session = Depends(get_db),
) -> dict:
    """Sentiment counts for the stat cards; ``meta.freshness`` drives the badge."""
    data = news_svc.summary(db, days=days)
    freshness = data.pop("freshness", None)
    return envelope(data, freshness=freshness)
