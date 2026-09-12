"""研报库 (research library) + ratings + recommendation pools."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.api.common import clamp_page, envelope, paged, parse_date
from app.core.db import get_db
from app.models.research import RatingEvent, ResearchReport
from app.services.aggregation import research_facets, research_reports_query

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/reports")
def reports(
    keyword: Optional[str] = None,
    org: Optional[str] = None,
    industry: Optional[str] = None,
    rating: Optional[str] = None,
    code: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    sort: str = Query(default="-publish_date"),
    db: Session = Depends(get_db),
) -> dict:
    page, size = clamp_page(page, size)
    rows, total = research_reports_query(
        db, keyword=keyword, org=org, industry=industry, rating=rating, code=code,
        start=parse_date(start), end=parse_date(end), page=page, size=size, sort=sort,
    )
    return paged(rows, total, page, size)


@router.get("/facets")
def facets(db: Session = Depends(get_db)) -> dict:
    return envelope(research_facets(db))


@router.get("/ratings")
def ratings(
    date_: Optional[str] = Query(default=None, alias="date"),
    org: Optional[str] = None,
    code: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    page, size = clamp_page(page, size)
    q = select(RatingEvent)
    d: Optional[date] = parse_date(date_)
    if d:
        q = q.where(RatingEvent.trade_date == d)
    if org:
        q = q.where(RatingEvent.org == org)
    if code:
        q = q.where(RatingEvent.code == code)
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    q = q.order_by(desc(RatingEvent.trade_date)).offset((page - 1) * size).limit(size)
    rows = [
        {"code": r.code, "name": r.name, "trade_date": r.trade_date.isoformat(),
         "org": r.org, "analyst": r.analyst, "rating": r.rating, "rating_norm": r.rating_norm,
         "prev_rating": r.prev_rating, "rating_change": r.rating_change, "is_first": r.is_first,
         "target_low": r.target_low, "target_high": r.target_high, "industry": r.industry}
        for r in db.scalars(q).all()
    ]
    return paged(rows, total, page, size)


@router.get("/orgs")
def orgs(limit: int = Query(default=200, le=500), db: Session = Depends(get_db)) -> dict:
    """Report counts per institution (drives filters + 周统计)."""
    rows = db.execute(
        select(ResearchReport.org, func.count())
        .where(ResearchReport.org.isnot(None))
        .group_by(ResearchReport.org).order_by(desc(func.count())).limit(limit)
    ).all()
    return envelope([{"org": o, "count": c} for o, c in rows])
