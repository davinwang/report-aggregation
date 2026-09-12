"""Quote loading — turn stored DailyQuote rows into a pandas OHLCV frame.

Adjust priority lets one endpoint serve stocks (前复权 qfq preferred), the daily spot
snapshot (raw), and indices (none) without callers knowing the storage detail.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.market import DailyQuote
from app.models.security import Security

ADJUST_PRIORITY = ["qfq", "raw", "none", "hfq", ""]


def _pick_adjust(session: Session, code: str, prefer: Optional[str]) -> Optional[str]:
    available = [
        a for (a,) in session.execute(
            select(DailyQuote.adjust).where(DailyQuote.code == code).group_by(DailyQuote.adjust)
        ).all()
    ]
    if not available:
        return None
    if prefer and prefer in available:
        return prefer
    for a in ADJUST_PRIORITY:
        if a in available:
            return a
    return available[0]


def load_bars(session: Session, code: str, limit: int = 400,
              prefer_adjust: Optional[str] = None) -> pd.DataFrame:
    """Load the most recent ``limit`` bars for ``code`` as an OHLCV DataFrame.

    Columns: date, open, high, low, close, volume, amount, turnover_rate (+ oi if present).
    Returns an empty DataFrame when no data exists.
    """
    adjust = _pick_adjust(session, code, prefer_adjust)
    if adjust is None:
        return pd.DataFrame()
    q = (select(DailyQuote).where(DailyQuote.code == code, DailyQuote.adjust == adjust)
         .order_by(desc(DailyQuote.trade_date)).limit(limit))
    rows = session.scalars(q).all()
    if not rows:
        return pd.DataFrame()
    rows = list(reversed(rows))  # ascending by date
    df = pd.DataFrame([{
        "date": r.trade_date.isoformat(),
        "open": r.open, "high": r.high, "low": r.low, "close": r.close,
        "pre_close": r.pre_close, "volume": r.volume or 0.0, "amount": r.amount,
        "turnover_rate": r.turnover_rate, "change_pct": r.change_pct,
    } for r in rows])
    return df


def get_security(session: Session, code: str) -> Optional[Security]:
    return session.scalar(select(Security).where(Security.code == code))


def latest_quote(session: Session, code: str) -> Optional[DailyQuote]:
    return session.scalar(
        select(DailyQuote).where(DailyQuote.code == code)
        .order_by(desc(DailyQuote.trade_date)).limit(1)
    )
