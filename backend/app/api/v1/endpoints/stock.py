"""个股详情 (stock detail) — aggregates quote + financials + reports + ratings + flow."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.common import clamp_page, paged
from app.core.db import get_db
from app.models.flow import FundFlowDaily
from app.services.aggregation import research_reports_query, stock_detail

router = APIRouter(prefix="/api/stock", tags=["stock"])


@router.get("/{code}")
def detail(code: str, db: Session = Depends(get_db)) -> dict:
    data = stock_detail(db, code)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Security '{code}' not found")
    return {"data": data, "meta": {"code": code}}


@router.get("/{code}/reports")
def reports(
    code: str,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    page, size = clamp_page(page, size)
    rows, total = research_reports_query(db, code=code, page=page, size=size)
    return paged(rows, total, page, size, code=code)


@router.get("/{code}/flow")
def flow(code: str, limit: int = Query(default=30, ge=1, le=120), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(FundFlowDaily).where(FundFlowDaily.code == code)
        .order_by(desc(FundFlowDaily.trade_date)).limit(limit)
    ).all()
    return {"data": [{
        "trade_date": r.trade_date.isoformat(), "close": r.close, "change_pct": r.change_pct,
        "main_net_inflow": r.main_net_inflow, "super_large_net": r.super_large_net,
        "large_net": r.large_net, "medium_net": r.medium_net, "small_net": r.small_net,
    } for r in rows], "meta": {"code": code, "count": len(rows)}}
