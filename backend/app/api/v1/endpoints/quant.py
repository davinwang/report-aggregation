"""技术指标 (quant) endpoints — K-line series + all-market matrix.

``/api/quant/series`` mirrors the reference's server-computed indicator API; indicators
are computed in Python (services.indicators) over stored bars and returned ECharts-ready.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.cache import cache_get, cache_set
from app.core.db import get_db
from app.models.market import DailyQuote
from app.models.security import Security
from app.services.indicators import DEFAULT_INDICATORS, build_series, compute
from app.services.quotes import load_bars, load_bars_bulk

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


def _state(row_close: Optional[float], ma20: Optional[float], dif: Optional[float],
           dea: Optional[float], rsi: Optional[float]) -> dict:
    trend = "多" if (ma20 is not None and row_close is not None and row_close >= ma20) else "空"
    macd_state = "金叉" if (dif is not None and dea is not None and dif >= dea) else "死叉"
    rsi_state = "强" if (rsi is not None and rsi >= 60) else ("弱" if (rsi is not None and rsi <= 40) else "中")
    return {"trend": trend, "macd": macd_state, "rsi": rsi_state}


@router.get("/matrix")
def matrix(
    freq: str = Query(default="daily"),
    limit: int = Query(default=60, ge=1, le=300),
    scope: str = Query(default="index+active", description="index|index+active"),
    db: Session = Depends(get_db),
) -> dict:
    """Technical snapshot matrix across a bounded set of securities (全市场速览).

    Heavy aggregation (bars -> indicators for up to ``limit`` symbols). The ready
    payload stays cached until new data lands (SQLite mtime check, plus a 30-min
    safety TTL), so repeated page loads render instantly while data still comes
    from the local DB.
    """
    cache_key = f"quant.matrix:{scope}:{limit}"
    cached_rows = cache_get(cache_key)
    if cached_rows is not None:
        return envelope(cached_rows, freq=freq, count=len(cached_rows))

    codes: list[str] = list(db.scalars(select(Security.code).where(Security.type == "index")).all())
    if scope == "index+active":
        codes += _recent_active_codes(db, exclude=codes, limit=limit)
    codes = codes[:limit]

    name_map = {s.code: s.name for s in db.scalars(select(Security).where(Security.code.in_(codes))).all()}
    frames = load_bars_bulk(db, codes, limit=120)
    rows: list[dict] = []
    for code in codes:
        df = frames.get(code)
        if df is None or df.empty:
            continue
        ind = compute(df, ["ma", "macd", "rsi"])
        close = float(df["close"].iloc[-1])
        ma20 = _last(ind.get("ma"), "ma20")
        dif = _last(ind.get("macd"), "macd_dif")
        dea = _last(ind.get("macd"), "macd_dea")
        rsi = _last(ind.get("rsi"), "rsi12")
        rows.append({"code": code, "name": name_map.get(code, code), "close": round(close, 2),
                     "ma20": ma20, "rsi12": rsi, **_state(close, ma20, dif, dea, rsi)})
    cache_set(cache_key, rows)
    return envelope(rows, freq=freq, count=len(rows))


#: Recent-activity window for the 活跃个股 pick: sessions within N days of the
#: latest stored date. The window keeps the pick on ix_daily_quote_date (a few
#: thousand rows) instead of scanning the whole 258k-row code index — the
#: dominant cold-read cost on the bind-mounted deployment DB (198ms -> ~4ms).
RECENT_WINDOW_DAYS = 7

#: ``INDEXED BY`` pins the plan to the date index (with_hint does not render for
#: SQLite SELECTs); without it the planner scans the covering (code, trade_date)
#: index in full before applying the window filter.
_PICK_ACTIVE_SQL = text(
    "SELECT code FROM daily_quote INDEXED BY ix_daily_quote_date "
    "WHERE trade_date >= :since AND code NOT IN :exclude "
    "GROUP BY code ORDER BY MAX(trade_date) DESC LIMIT :lim"
).bindparams(bindparam("exclude", expanding=True))


def _recent_active_codes(db: Session, exclude: list[str], limit: int) -> list[str]:
    """Most recently traded stock codes (newest first), bounded to a recent window."""
    ref = db.scalar(select(func.max(DailyQuote.trade_date)))
    if ref is None:
        return []
    since = ref - timedelta(days=RECENT_WINDOW_DAYS)
    rows = db.execute(
        _PICK_ACTIVE_SQL,
        # "" placeholder keeps NOT IN non-empty (an empty expanding IN matches nothing).
        {"since": since, "exclude": exclude or [""], "lim": limit},
    ).all()
    return [c for (c,) in rows]


def _last(frame: Optional[pd.DataFrame], col: str) -> Optional[float]:
    if frame is None or col not in frame.columns or frame.empty:
        return None
    v = frame[col].iloc[-1]
    try:
        f = float(v)
        return None if pd.isna(f) else round(f, 3)
    except (TypeError, ValueError):
        return None
