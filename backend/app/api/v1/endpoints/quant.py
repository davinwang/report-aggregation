"""技术指标 (quant) endpoints — K-line series + all-market matrix.

``/api/quant/series`` mirrors the reference's server-computed indicator API; indicators
are computed in Python (services.indicators) over stored bars and returned ECharts-ready.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.db import get_db
from app.services import matrix as matrix_svc
from app.services.indicators import DEFAULT_INDICATORS, build_series
from app.services.quotes import load_bars

router = APIRouter(prefix="/api/quant", tags=["quant"])

WARMUP = 80  # extra bars loaded before the requested window for indicator warmup

# Period string → approximate trading days.
_PERIOD_MAP: dict[str, int] = {
    "6m": 120,
    "1y": 250,
    "2y": 500,
    "3y": 750,
    "5y": 1250,
}


def _resolve_bars(period: str) -> int:
    """Convert a human-friendly period like '6m'/'1y' to trading-day count."""
    if period in _PERIOD_MAP:
        return _PERIOD_MAP[period]
    # Fallback: try interpreting as a plain integer (legacy `bars` value).
    try:
        return max(10, min(int(period), 1500))
    except (ValueError, TypeError):
        return 250


@router.get("/series")
def series(
    code: str = Query(..., description="security code, e.g. 600519 or sh000300"),
    freq: str = Query(default="daily"),
    indicators: Optional[str] = Query(default=None, description="comma-separated, e.g. ma,macd,kdj"),
    period: str = Query(default="1y", description="lookback period: 6m|1y|2y|3y|5y"),
    adjust: Optional[str] = Query(default=None, description="qfq|hfq|raw|none"),
    db: Session = Depends(get_db),
) -> dict:
    names = [x for x in (indicators or "").split(",") if x] or DEFAULT_INDICATORS
    bars = _resolve_bars(period)
    df = load_bars(db, code, limit=bars + WARMUP, prefer_adjust=adjust)
    payload = build_series(df, names=names, bars=bars, code=code)
    return envelope(payload, freq=freq, indicators=names, count=len(payload["dates"]))


@router.get("/matrix")
def matrix(
    freq: str = Query(default="daily"),
    limit: int = Query(default=60, ge=1, le=300),
    scope: str = Query(default="index+active", description="index|index+active"),
    db: Session = Depends(get_db),
) -> dict:
    """Technical snapshot matrix across a bounded set of securities (全市场速览).

    Computation + caching live in ``services.matrix`` so the MCP tool shares the
    same ready payload (same cache key); this route stays thin.
    """
    rows = matrix_svc.snapshot(db, scope=scope, limit=limit)
    return envelope(rows, freq=freq, count=len(rows))
