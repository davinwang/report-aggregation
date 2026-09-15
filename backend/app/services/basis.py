"""股指期货基差 (stock-index futures basis) — the stock analog of the reference's 期限结构.

Conventions (matching ``IndexFutureDaily``):

* ``basis`` = futures settle − underlying index close. ``basis > 0`` ⇒ 升水 (contango),
  ``basis < 0`` ⇒ 贴水 (backwardation).
* ``basis_annualized`` = ``basis / spot`` scaled to 365 days divided by days-to-expiry,
  expressed in percent.

CFFEX equity-index futures: IF→沪深300, IH→上证50, IC→中证500, IM→中证1000.
Contract expiry = the **third Friday** of the contract month (CFFEX rule).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.market import IndexFutureDaily

# variety -> (underlying sina code, display name)
VARIETY_UNDERLYING: dict[str, tuple[str, str]] = {
    "IF": ("sh000300", "沪深300"),
    "IH": ("sh000016", "上证50"),
    "IC": ("sh000905", "中证500"),
    "IM": ("sh000852", "中证1000"),
}
VARIETIES = list(VARIETY_UNDERLYING)

_SYMBOL_RE = re.compile(r"^([A-Z]{1,2})(\d{4})$")


def underlying_of(symbol: str) -> Optional[tuple[str, str]]:
    """Return ``(sina_code, display_name)`` for a contract symbol, or None."""
    m = _SYMBOL_RE.match((symbol or "").strip().upper())
    return VARIETY_UNDERLYING.get(m.group(1)) if m else None


def variety_of(symbol: str) -> Optional[str]:
    m = _SYMBOL_RE.match((symbol or "").strip().upper())
    return m.group(1) if m else None


def third_friday(year: int, month: int) -> date:
    """CFFEX contract expiry: the third Friday of the contract month."""
    first = date(year, month, 1)
    first_friday = first + timedelta(days=(4 - first.weekday()) % 7)
    return first_friday + timedelta(days=14)


def contract_expiry(symbol: str) -> Optional[date]:
    """Parse the expiry date from a CFFEX contract symbol (e.g. ``IF2412`` → 2024-12-20)."""
    m = _SYMBOL_RE.match((symbol or "").strip().upper())
    if not m:
        return None
    yy, mm = int(m.group(2)[:2]), int(m.group(2)[2:])
    if not 1 <= mm <= 12:
        return None
    return third_friday(2000 + yy, mm)


def days_to_expiry(symbol: str, ref: date) -> Optional[int]:
    exp = contract_expiry(symbol)
    return (exp - ref).days if exp else None


def compute_basis(
    settle: Optional[float],
    spot: Optional[float],
    symbol: str,
    ref: date,
) -> tuple[Optional[float], Optional[float], Optional[date], Optional[int]]:
    """Return ``(basis, basis_annualized_pct, expiry, days_to_expiry)``.

    Any missing input degrades gracefully to ``None`` for the derived values.
    """
    expiry = contract_expiry(symbol)
    dte = (expiry - ref).days if expiry else None
    if settle is None or spot is None:
        return None, None, expiry, dte
    basis = settle - spot
    annualized: Optional[float] = None
    if spot and dte and dte > 0:
        annualized = round(basis / spot * (365.0 / dte) * 100.0, 3)
    return round(basis, 3), annualized, expiry, dte


# ----------------------------- read helpers (API) -----------------------------
def latest_date(session: Session, variety: Optional[str] = None) -> Optional[date]:
    q = select(IndexFutureDaily.trade_date).order_by(desc(IndexFutureDaily.trade_date)).limit(1)
    if variety:
        q = select(IndexFutureDaily.trade_date).where(IndexFutureDaily.variety == variety).order_by(
            desc(IndexFutureDaily.trade_date)
        ).limit(1)
    return session.scalar(q)


def term_structure(session: Session, variety: str, ref: Optional[date] = None) -> dict:
    """All contracts of ``variety`` on the reference date, ordered by expiry."""
    ref = ref or latest_date(session, variety)
    if ref is None:
        return {"trade_date": None, "contracts": []}
    rows = session.scalars(
        select(IndexFutureDaily)
        .where(IndexFutureDaily.variety == variety, IndexFutureDaily.trade_date == ref)
        .order_by(IndexFutureDaily.symbol)
    ).all()
    contracts = []
    for r in rows:
        exp = contract_expiry(r.symbol)
        contracts.append({
            "symbol": r.symbol,
            "expiry": exp.isoformat() if exp else None,
            "days_to_expiry": (exp - ref).days if exp else None,
            "open": r.open, "high": r.high, "low": r.low, "close": r.close,
            "settle": r.settle, "pre_settle": r.pre_settle,
            "volume": r.volume, "oi": r.oi,
            "basis": r.basis, "basis_annualized": r.basis_annualized,
            "underlying_index_close": r.underlying_index_close,
        })
    contracts.sort(key=lambda c: c["days_to_expiry"] if c["days_to_expiry"] is not None else 9999)
    spot = next((c["underlying_index_close"] for c in contracts if c["underlying_index_close"]), None)
    return {"trade_date": ref.isoformat(), "spot": spot, "contracts": contracts}


def main_contract(contracts: list[dict]) -> Optional[dict]:
    """The near-month contract with the largest open interest (front-month proxy)."""
    live = [c for c in contracts if (c.get("days_to_expiry") or 9999) >= 0 and (c.get("oi") or 0) > 0]
    pool = live or contracts
    return max(pool, key=lambda c: c.get("oi") or 0) if pool else None


def history(session: Session, variety: str, days: int = 60) -> dict:
    """Front-month basis trend: one point per trade date (largest-OI contract that day)."""
    ref = latest_date(session, variety)
    if ref is None:
        return {"dates": [], "basis": [], "basis_annualized": [], "spot": [], "symbols": []}
    since = ref - timedelta(days=max(7, days * 2))  # generous window (trading vs calendar days)
    rows = session.scalars(
        select(IndexFutureDaily)
        .where(IndexFutureDaily.variety == variety, IndexFutureDaily.trade_date >= since)
        .order_by(IndexFutureDaily.trade_date)
    ).all()
    by_date: dict[date, list[IndexFutureDaily]] = {}
    for r in rows:
        by_date.setdefault(r.trade_date, []).append(r)
    dates, basis, ann, spot, symbols = [], [], [], [], []
    for d in sorted(by_date):
        pick = max(by_date[d], key=lambda r: r.oi or 0)
        dates.append(d.isoformat())
        basis.append(pick.basis)
        ann.append(pick.basis_annualized)
        spot.append(pick.underlying_index_close)
        symbols.append(pick.symbol)
    if len(dates) > days:
        dates, basis, ann, spot, symbols = dates[-days:], basis[-days:], ann[-days:], spot[-days:], symbols[-days:]
    return {"dates": dates, "basis": basis, "basis_annualized": ann, "spot": spot, "symbols": symbols}


def overview(session: Session, ref: Optional[date] = None) -> list[dict]:
    """Per-variety front-month basis snapshot for the dashboard."""
    out: list[dict] = []
    for v in VARIETIES:
        ts = term_structure(session, v, ref)
        main = main_contract(ts["contracts"])
        code, name = VARIETY_UNDERLYING[v]
        out.append({
            "variety": v,
            "underlying_code": code,
            "underlying_name": name,
            "trade_date": ts["trade_date"],
            "spot": ts["spot"],
            "symbol": main["symbol"] if main else None,
            "basis": main["basis"] if main else None,
            "basis_annualized": main["basis_annualized"] if main else None,
            "oi": main["oi"] if main else None,
            "volume": main["volume"] if main else None,
            "days_to_expiry": main["days_to_expiry"] if main else None,
            "state": (
                None if not main or main["basis"] is None
                else ("升水" if main["basis"] > 0 else "贴水" if main["basis"] < 0 else "平水")
            ),
        })
    return out
