"""板块/指数联动 (linkage) — index correlation matrix + individual-stock Beta.

Provides:

* **指数相关性** — Pearson correlation of daily returns across the tracked
  benchmark indices, aligned on their common trading days.
* **个股Beta** — per-stock β (and ρ²) versus 沪深300 over a rolling window,
  computed from stored 前复权 close series.

All computations are read-only over ``daily_quote``; no snapshots are stored.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.market import DailyQuote
from app.models.security import Security

BENCHMARK_CODE = "sh000300"
DEFAULT_WINDOW = 120


def _load_series(
    session: Session, code: str, window: int,
) -> tuple[list[date], np.ndarray]:
    """Last ``window+1`` closes for a code (oldest → newest)."""
    rows = session.execute(
        select(DailyQuote.trade_date, DailyQuote.close)
        .where(DailyQuote.code == code, DailyQuote.close.isnot(None))
        .order_by(desc(DailyQuote.trade_date))
        .limit(window + 1)
    ).all()
    rows.reverse()
    return [d for d, _c in rows], np.array([float(c) for _d, c in rows])


def _returns(dates: list[date], closes: np.ndarray) -> tuple[list[date], np.ndarray]:
    """Simple daily returns aligned to the later date of each pair."""
    if len(closes) < 2:
        return [], np.array([])
    rets = closes[1:] / closes[:-1] - 1.0
    return dates[1:], rets


def correlation_matrix(
    session: Session, window: int = DEFAULT_WINDOW,
) -> dict[str, Any]:
    """Correlation of daily returns across indices with stored history."""
    codes = [
        r for (r,) in session.execute(
            select(Security.code).where(Security.type == "index").order_by(Security.code)
        ).all()
    ]
    name_map = {
        s.code: s.name
        for s in session.scalars(select(Security).where(Security.code.in_(codes))).all()
    }

    series: dict[str, tuple[list[date], np.ndarray]] = {}
    for code in codes:
        dates, rets = _returns(*_load_series(session, code, window))
        if len(rets) >= max(20, window // 4):
            series[code] = (dates, rets)

    if len(series) < 2:
        return {"ref": None, "window": window, "codes": [], "names": [], "matrix": [], "pairs": []}

    # Align on common dates (most indices share the trading calendar).
    common: set[date] | None = None
    for dates, _r in series.values():
        common = set(dates) if common is None else (common & set(dates))
    common_dates = sorted(common or [])
    ref = common_dates[-1] if common_dates else None

    kept = [c for c in series if len(series[c][0]) == len(common_dates)]
    kept = sorted(kept)
    stacked: dict[str, list[float]] = {}
    for code in kept:
        dates, rets = series[code]
        idx = {d: i for i, d in enumerate(dates)}
        stacked[code] = [float(rets[idx[d]]) for d in common_dates]

    n = len(kept)
    matrix: list[list[float | None]] = []
    for i in range(n):
        row: list[float | None] = []
        a = np.array(stacked[kept[i]])
        for j in range(n):
            b = np.array(stacked[kept[j]])
            if a.std() == 0 or b.std() == 0:
                row.append(None)
            else:
                row.append(round(float(np.corrcoef(a, b)[0, 1]), 3))
        matrix.append(row)

    # Strongest |corr| pairs (excluding the diagonal).
    pairs: list[dict[str, Any]] = []
    for i in range(n):
        for j in range(i + 1, n):
            v = matrix[i][j]
            if v is not None:
                pairs.append({
                    "a": kept[i], "a_name": name_map.get(kept[i], kept[i]),
                    "b": kept[j], "b_name": name_map.get(kept[j], kept[j]),
                    "corr": v,
                })
    pairs.sort(key=lambda p: abs(p["corr"]), reverse=True)

    return {
        "ref": ref.isoformat() if ref else None,
        "window": window,
        "samples": len(common_dates),
        "codes": kept,
        "names": [name_map.get(c, c) for c in kept],
        "matrix": matrix,
        "pairs": pairs[:10],
    }


def beta_table(
    session: Session,
    benchmark: str = BENCHMARK_CODE,
    window: int = DEFAULT_WINDOW,
    limit: int = 100,
) -> dict[str, Any]:
    """β / ρ² of stocks versus the benchmark over the rolling window."""
    b_dates, b_closes = _load_series(session, benchmark, window)
    # strict=True: _returns pairs dates[i+1] with rets[i], so a length mismatch means a
    # corrupt series — zip's default truncation would build a dict keyed by the wrong
    # dates and silently shift the whole beta computation.
    b_rets_map = dict(zip(*_returns(b_dates, b_closes), strict=True))
    if not b_rets_map:
        return {"ref": None, "benchmark": benchmark, "window": window, "rows": []}

    codes = list(session.execute(
        select(DailyQuote.code)
        .where(DailyQuote.adjust == "qfq", DailyQuote.close.isnot(None))
        .group_by(DailyQuote.code)
        .order_by(desc(func.count()))
        .limit(limit)
    ).scalars().all())
    if not codes:
        return {"ref": None, "benchmark": benchmark, "window": window, "rows": []}

    name_map = {
        s.code: s.name
        for s in session.scalars(select(Security).where(Security.code.in_(codes))).all()
    }

    rows: list[dict[str, Any]] = []
    ref: date | None = None
    for code in codes:
        s_dates, s_closes = _load_series(session, code, window)
        rets = dict(zip(*_returns(s_dates, s_closes), strict=True))
        common = sorted(set(rets) & set(b_rets_map))
        if len(common) < 20:
            continue
        ref = max(ref, common[-1]) if ref else common[-1]
        s = np.array([rets[d] for d in common])
        b = np.array([b_rets_map[d] for d in common])
        var_b = float(b.var())
        if var_b == 0:
            continue
        beta = float(np.cov(s, b, ddof=0)[0, 1] / var_b)
        corr = float(np.corrcoef(s, b)[0, 1])
        rows.append({
            "code": code,
            "name": name_map.get(code, code),
            "beta": round(beta, 3),
            "corr": round(corr, 3),
            "r2": round(corr * corr, 3),
            "vol": round(float(s.std() * np.sqrt(252)), 4),
            "samples": len(common),
        })
    rows.sort(key=lambda r: r["beta"], reverse=True)
    return {
        "ref": ref.isoformat() if ref else None,
        "benchmark": benchmark,
        "benchmark_name": (session.scalar(
            select(Security.name).where(Security.code == benchmark)) or benchmark),
        "window": window,
        "rows": rows,
    }
