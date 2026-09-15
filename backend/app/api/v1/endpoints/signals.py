"""可操作信号 (actionable signals) — rule-based rating/target/consensus screen (Phase 2).

``POST /refresh`` recomputes the Signal table from 东财研报 history; the read
endpoints page/filter the stored signals. No LLM involved (AI deferred).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import clamp_page, envelope, paged, parse_date
from app.core.db import get_db
from app.services import signals as signals_svc

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
def signals_list(
    action: Optional[str] = Query(default=None, description="upgrade|downgrade|first|consensus"),
    industry: Optional[str] = None,
    days: int = Query(default=30, ge=1, le=365),
    date_: Optional[str] = Query(default=None, alias="date", description="exact session YYYY-MM-DD"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    page, size = clamp_page(page, size)
    rows, total, ref = signals_svc.list_signals(
        db, action=action, industry=industry, days=days,
        date_=parse_date(date_), page=page, size=size,
    )
    return paged(rows, total, page, size, ref=ref.isoformat() if ref else None, days=days)


@router.get("/summary")
def signals_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(signals_svc.summary(db, days))


@router.post("/refresh")
def signals_refresh(
    lookback_days: int = Query(default=180, ge=30, le=730),
    db: Session = Depends(get_db),
) -> dict:
    """Recompute upgrade/downgrade/first/consensus signals from stored reports."""
    stats = signals_svc.refresh_signals(db, lookback_days=lookback_days)
    db.commit()
    return envelope(stats)


@router.get("/types")
def signal_types() -> dict:
    """Signal vocabulary for the UI filters."""
    return envelope([
        {"value": "upgrade", "label": "评级上调"},
        {"value": "downgrade", "label": "评级下调"},
        {"value": "first", "label": "首次覆盖"},
        {"value": "consensus", "label": "一致评级"},
    ])
