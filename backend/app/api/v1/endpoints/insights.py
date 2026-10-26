"""研报洞察 (research insights) — 情绪分歧 / 信号复盘 / 龙虎榜联动 read endpoints.

All three are rule-based aggregations over stored tables (no LLM, no new
ingestion feeds). Freshness piggybacks on the underlying feeds:
``research_reports`` for sentiment, ``ratings_daily`` for replay,
``lhb`` for the LHB×research join.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.db import get_db
from app.services import insights as svc

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/sentiment")
def sentiment(
    days: int = Query(default=30, ge=7, le=180),
    min_reports: int = Query(default=2, ge=1, le=20),
    order: str = Query(default="dispersion", description="dispersion|consensus"),
    limit: int = Query(default=200, ge=5, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """Per-stock 研报情绪与分歧度 (consensus / dispersion across orgs)."""
    return envelope(svc.sentiment(db, days=days, min_reports=min_reports, limit=limit, order=order))


@router.get("/replay")
def replay(
    horizon: int = Query(default=20, ge=5, le=60, description="forward window in trading days"),
    days: int = Query(default=90, ge=30, le=365, description="signal lookback in calendar days"),
    kind: str | None = Query(default=None, description="upgrade|downgrade|first|consensus"),
    limit: int = Query(default=100, ge=5, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """信号复盘 — closed signals scored by forward excess return vs 沪深300."""
    return envelope(svc.replay(db, horizon=horizon, days=days, kind=kind, limit=limit))


@router.get("/lhb-research")
def lhb_research(
    lhb_days: int = Query(default=10, ge=1, le=60),
    window_days: int = Query(default=30, ge=7, le=90),
    direction: str | None = Query(default=None, description="buy|sell"),
    limit: int = Query(default=100, ge=5, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """龙虎榜×研报联动 — LHB stocks with recent research coverage (双重信号)."""
    return envelope(svc.lhb_research(db, lhb_days=lhb_days, window_days=window_days,
                                     direction=direction, limit=limit))
