"""全市场速览 matrix — technical snapshot across a bounded set of securities.

Extracted from the ``/api/quant/matrix`` endpoint so the HTTP route and the MCP
tool share one implementation *and* one read cache (key
``quant.matrix:{scope}:{limit}``). Heavy aggregation (bars -> indicators for up
to ``limit`` symbols); the ready payload stays cached until new data lands (DB
change-counter check, plus a 30-min safety TTL), so repeated callers render
instantly while data still comes from the local DB.
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
from sqlalchemy import bindparam, func, select, text
from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.models.market import DailyQuote
from app.models.security import Security
from app.services.indicators import compute
from app.services.quotes import load_bars_bulk

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


def snapshot(session: Session, scope: str = "index+active", limit: int = 60) -> list[dict]:
    """Cached technical snapshot rows across indices (+ recent-active stocks)."""
    cache_key = f"quant.matrix:{scope}:{limit}"
    cached_rows = cache_get(cache_key)
    if cached_rows is not None:
        return cached_rows

    codes: list[str] = list(session.scalars(select(Security.code).where(Security.type == "index")).all())
    if scope == "index+active":
        codes += _recent_active_codes(session, exclude=codes, limit=limit)
    codes = codes[:limit]

    name_map = {
        s.code: s.name
        for s in session.scalars(select(Security).where(Security.code.in_(codes))).all()
    }
    frames = load_bars_bulk(session, codes, limit=120)
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
    return rows


def _recent_active_codes(session: Session, exclude: list[str], limit: int) -> list[str]:
    """Most recently traded stock codes (newest first), bounded to a recent window."""
    ref = session.scalar(select(func.max(DailyQuote.trade_date)))
    if ref is None:
        return []
    since = ref - timedelta(days=RECENT_WINDOW_DAYS)
    rows = session.execute(
        _PICK_ACTIVE_SQL,
        # "" placeholder keeps NOT IN non-empty (an empty expanding IN matches nothing).
        {"since": since, "exclude": exclude or [""], "lim": limit},
    ).all()
    return [c for (c,) in rows]


def _state(row_close: float | None, ma20: float | None, dif: float | None,
           dea: float | None, rsi: float | None) -> dict:
    trend = "多" if (ma20 is not None and row_close is not None and row_close >= ma20) else "空"
    macd_state = "金叉" if (dif is not None and dea is not None and dif >= dea) else "死叉"
    rsi_state = "强" if (rsi is not None and rsi >= 60) else (
        "弱" if (rsi is not None and rsi <= 40) else "中")
    return {"trend": trend, "macd": macd_state, "rsi": rsi_state}


def _last(frame: pd.DataFrame | None, col: str) -> float | None:
    if frame is None or col not in frame.columns or frame.empty:
        return None
    v = frame[col].iloc[-1]
    try:
        f = float(v)
        return None if pd.isna(f) else round(f, 3)
    except (TypeError, ValueError):
        return None
