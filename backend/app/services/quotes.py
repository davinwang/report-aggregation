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


_BARS_COLUMNS = (
    DailyQuote.trade_date, DailyQuote.open, DailyQuote.high, DailyQuote.low,
    DailyQuote.close, DailyQuote.pre_close, DailyQuote.volume, DailyQuote.amount,
    DailyQuote.turnover_rate, DailyQuote.change_pct,
)


def load_bars_bulk(session: Session, codes: list[str], limit: int = 400,
                   prefer_adjust: Optional[str] = None) -> dict[str, pd.DataFrame]:
    """Tail-load many symbols in one pass, mirroring :func:`load_bars` per code.

    Resolves the adjust per code with a single grouped query, then reads each
    symbol's tail as column tuples (no ORM entity hydration) — the per-code
    seek is index-backed (``ix_daily_quote_code_adj_date``) and needs no sort,
    so a 60-symbol matrix costs milliseconds per symbol instead of ~60ms.
    """
    codes = [c for c in dict.fromkeys(codes) if c]
    if not codes:
        return {}

    available: dict[str, list[str]] = {}
    for code, adjust in session.execute(
        select(DailyQuote.code, DailyQuote.adjust).where(DailyQuote.code.in_(codes))
        .group_by(DailyQuote.code, DailyQuote.adjust)
    ).all():
        available.setdefault(code, []).append(adjust or "")

    out: dict[str, pd.DataFrame] = {}
    for code in codes:
        adjust = _choose_adjust(available.get(code, []), prefer_adjust)
        if adjust is None:
            continue
        rows = session.execute(
            select(*_BARS_COLUMNS)
            .where(DailyQuote.code == code, DailyQuote.adjust == adjust)
            .order_by(desc(DailyQuote.trade_date)).limit(limit)
        ).all()
        if not rows:
            continue
        out[code] = pd.DataFrame([{
            "date": r[0].isoformat(),
            "open": r[1], "high": r[2], "low": r[3], "close": r[4],
            "pre_close": r[5], "volume": r[6] or 0.0, "amount": r[7],
            "turnover_rate": r[8], "change_pct": r[9],
        } for r in reversed(rows)])
    return out


def _choose_adjust(available: list[str], prefer: Optional[str]) -> Optional[str]:
    """Same precedence as :func:`_pick_adjust`, over a pre-fetched list."""
    if not available:
        return None
    if prefer and prefer in available:
        return prefer
    for a in ADJUST_PRIORITY:
        if a in available:
            return a
    return available[0]


def get_security(session: Session, code: str) -> Optional[Security]:
    return session.scalar(select(Security).where(Security.code == code))


def latest_quote(session: Session, code: str) -> Optional[DailyQuote]:
    return session.scalar(
        select(DailyQuote).where(DailyQuote.code == code)
        .order_by(desc(DailyQuote.trade_date)).limit(1)
    )
