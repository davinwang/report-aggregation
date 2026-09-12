"""市场看板 (market dashboard) endpoint."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import envelope, parse_date
from app.core.db import get_db
from app.services.aggregation import market_dashboard

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/dashboard")
def dashboard(
    period: str = Query(default="week", description="today|week|twoweek|month"),
    date_: Optional[str] = Query(default=None, alias="date", description="reference date YYYY-MM-DD"),
    sector: Optional[str] = Query(default=None, description="industry group filter"),
    db: Session = Depends(get_db),
) -> dict:
    ref: Optional[date] = parse_date(date_)
    data = market_dashboard(db, period=period, ref=ref, sector=sector)
    return envelope(data, period=period, sector=sector)
