"""股指期权 (stock-index options) — T型报价 shaping.

CFFEX index options via ``option_finance_board(symbol=..., end_month=...)``: the raw
frame carries ``instrument`` (e.g. ``IO2612-C-3900``), ``lastprice``, ``updown``,
``volume``, ``position`` (持仓量) and bid/ask — the strike and call/put flag live inside
the instrument code, so everything is parsed here.

The T-board pivots the flat contract list into one row per strike with call columns on
the left and put columns on the right (the reference platform's T型报价), plus PCR
(put/call ratio) totals by 持仓量 and 成交量.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.market import DailyQuote, OptionQuote

# CFFEX equity-index option underlyings -> (variety, underlying sina code)
UNDERLYINGS: dict[str, tuple[str, str]] = {
    "沪深300股指期权": ("IO", "sh000300"),
    "中证1000股指期权": ("MO", "sh000852"),
    "上证50股指期权": ("HO", "sh000016"),
}
UNDERLYING_NAMES = list(UNDERLYINGS)

# IO2612-C-3900 / HO2612-P-2500 (tolerant of the hyphen being absent)
_INSTRUMENT_RE = re.compile(r"^([A-Z]{1,2})(\d{4})-?([CP])-?(\d+(?:\.\d+)?)$")


def parse_instrument(instrument: str) -> Optional[dict]:
    """Split ``IO2612-C-3900`` into ``{variety, end_month, cp, strike}`` (cp: call|put)."""
    m = _INSTRUMENT_RE.match((instrument or "").strip().upper())
    if not m:
        return None
    variety, end_month, cp, strike = m.groups()
    return {
        "variety": variety,
        "end_month": end_month,
        "cp": "call" if cp == "C" else "put",
        "strike": float(strike),
    }


def months_for_ref(ref: date, count: int = 5) -> list[str]:
    """Candidate contract months (YYYY→YYMM) starting at ``ref``'s month."""
    out: list[str] = []
    y, m = ref.year, ref.month
    for _ in range(count):
        out.append(f"{y % 100:02d}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def latest_trade_date(session: Session) -> Optional[date]:
    """Newest stored trade date (used to stamp live option snapshots)."""
    return session.scalar(select(func.max(DailyQuote.trade_date)))


# ----------------------------- read helpers (API) -----------------------------
def _spot(session: Session, under_code: str, ref: Optional[date] = None) -> Optional[float]:
    ref = ref or latest_trade_date(session)
    if ref is None:
        return None
    return session.scalar(
        select(DailyQuote.close)
        .where(DailyQuote.code == under_code, DailyQuote.trade_date == ref)
        .limit(1)
    )


def available_months(session: Session, underlying: str, ref: Optional[date] = None) -> list[str]:
    """Contract months present in the DB for an underlying, newest first."""
    ref = ref or latest_trade_date(session)
    if ref is None:
        return []
    rows = session.scalars(
        select(OptionQuote.end_month)
        .where(OptionQuote.underlying == underlying, OptionQuote.trade_date == ref)
        .distinct()
    ).all()
    return sorted({m for m in rows if m}, reverse=True)


def board(session: Session, underlying: str, month: Optional[str] = None, ref: Optional[date] = None) -> dict:
    """T型报价: one row per strike with call/put legs + PCR totals."""
    ref = ref or latest_trade_date(session)
    months = available_months(session, underlying, ref)
    if month and month in months:
        chosen = month
    else:
        chosen = months[0] if months else None
    under_code = UNDERLYINGS.get(underlying, (None, None))[1]
    spot = _spot(session, under_code, ref) if under_code else None
    if ref is None or chosen is None:
        return {
            "underlying": underlying, "month": chosen, "months": months,
            "trade_date": ref.isoformat() if ref else None, "spot": spot,
            "atm_strike": None, "rows": [], "totals": {},
        }

    quotes = session.scalars(
        select(OptionQuote).where(
            OptionQuote.underlying == underlying,
            OptionQuote.trade_date == ref,
            OptionQuote.end_month == chosen,
        )
    ).all()

    by_strike: dict[float, dict] = {}
    call_oi = put_oi = call_vol = put_vol = 0.0
    for q in quotes:
        parsed = parse_instrument(q.contract_code)
        if parsed is None or q.strike is None:
            continue
        leg = {
            "contract_code": q.contract_code,
            "last": q.close,
            # 涨跌 = 最新价 − 昨结算价 (the feed provides the delta; the adapter
            # reconstructs pre_settle from it so no extra column is needed).
            "updown": round(q.close - q.pre_settle, 4)
            if (q.close is not None and q.pre_settle is not None)
            else None,
            "volume": q.volume,
            "oi": q.oi,
        }
        row = by_strike.setdefault(q.strike, {"strike": q.strike, "call": None, "put": None})
        row[parsed["cp"]] = leg
        if parsed["cp"] == "call":
            call_oi += q.oi or 0
            call_vol += q.volume or 0
        else:
            put_oi += q.oi or 0
            put_vol += q.volume or 0

    rows = [by_strike[k] for k in sorted(by_strike, reverse=True)]
    atm = None
    if spot and rows:
        atm = min((r["strike"] for r in rows), key=lambda s: abs(s - spot))

    return {
        "underlying": underlying,
        "variety": UNDERLYINGS.get(underlying, (None,))[0],
        "month": chosen,
        "months": months,
        "trade_date": ref.isoformat(),
        "spot": spot,
        "atm_strike": atm,
        "rows": rows,
        "totals": {
            "call_oi": call_oi or None,
            "put_oi": put_oi or None,
            "call_volume": call_vol or None,
            "put_volume": put_vol or None,
            "pcr_oi": round(put_oi / call_oi, 3) if call_oi else None,
            "pcr_volume": round(put_vol / call_vol, 3) if call_vol else None,
            "contracts": len(quotes),
        },
    }


def overview(session: Session, ref: Optional[date] = None) -> list[dict]:
    """Per-underlying snapshot: contracts, PCR by OI/volume, ATM strike."""
    out: list[dict] = []
    for name, (variety, code) in UNDERLYINGS.items():
        b = board(session, name, None, ref)
        out.append({
            "underlying": name,
            "variety": variety,
            "underlying_code": code,
            "trade_date": b["trade_date"],
            "month": b["month"],
            "spot": b["spot"],
            "atm_strike": b["atm_strike"],
            "pcr_oi": b["totals"].get("pcr_oi"),
            "pcr_volume": b["totals"].get("pcr_volume"),
            "call_oi": b["totals"].get("call_oi"),
            "put_oi": b["totals"].get("put_oi"),
        })
    return out
