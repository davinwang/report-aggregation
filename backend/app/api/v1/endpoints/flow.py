"""资金流向 (capital flow) — 沪深港通 / 融资融券 / 龙虎榜 (Phase 2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import clamp_page, envelope, paged, parse_date
from app.core.db import get_db
from app.services import flow as flow_svc

router = APIRouter(prefix="/api/flow", tags=["flow"])


@router.get("/summary")
def flow_summary(db: Session = Depends(get_db)) -> dict:
    return envelope(flow_svc.summary(db))


@router.get("/northbound")
def northbound(
    days: int = Query(default=30, ge=1, le=250),
    db: Session = Depends(get_db),
) -> dict:
    """沪深港通: per-board net flow + 涨跌家数 breadth over time."""
    return envelope(flow_svc.northbound_history(db, days), days=days)


@router.get("/margin")
def margin(
    days: int = Query(default=60, ge=5, le=250),
    db: Session = Depends(get_db),
) -> dict:
    """融资融券: SSE daily range (元) + SZSE latest snapshot."""
    return envelope(flow_svc.margin_history(db, days), days=days)


@router.get("/lhb")
def lhb(
    date_: str | None = Query(default=None, alias="date", description="session YYYY-MM-DD"),
    direction: str | None = Query(default=None, description="buy|sell"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """龙虎榜 daily detail ranked by 净买额."""
    page, size = clamp_page(page, size)
    data = flow_svc.lhb_query(db, ref=parse_date(date_), direction=direction, page=page, size=size)
    return paged(data["rows"], data["total"], page, size,
                 trade_date=data["trade_date"], stats=data["stats"])
