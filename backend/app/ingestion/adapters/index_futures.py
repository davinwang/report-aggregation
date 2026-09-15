"""index_futures — 中金所股指期货日线 (IF/IH/IC/IM) + 基差 via ``get_futures_daily``.

Fetches the CFFEX daily futures frame, keeps only equity-index varieties, links each
row to its underlying index close (from the ``index_daily`` bars already in the DB) and
computes ``basis`` / ``basis_annualized`` through ``services.basis``. This is the stock
analog of the reference platform's 期限结构 module.

Runs after ``index_daily`` in the bulk order so the spot leg is available.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_date, to_float
from app.models.market import DailyQuote, IndexFutureDaily
from app.services import basis as basis_svc

logger = get_logger(__name__)

# Equity-index varieties (CFFEX also lists treasury futures T/TF/TS — excluded).
VARIETIES = set(basis_svc.VARIETIES)

DEFAULT_LOOKBACK_DAYS = 60


def _parse_ymd(s: Any) -> Optional[date]:
    if not s:
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    txt = str(s).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    return to_date(txt)


class IndexFuturesAdapter(BaseAdapter):
    name = "index_futures"
    description = "中金所股指期货日线 IF/IH/IC/IM + 基差(升贴水)"

    def fetch(self, start: Any = None, end: Any = None, days: int = DEFAULT_LOOKBACK_DAYS, **kwargs) -> Any:
        ak = get_ak()
        end_d = _parse_ymd(end) or date.today()
        start_d = _parse_ymd(start) or (end_d - timedelta(days=max(7, days)))
        return ak.get_futures_daily(
            start_date=start_d.strftime("%Y%m%d"),
            end_date=end_d.strftime("%Y%m%d"),
            market="CFFEX",
        )

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            symbol = (clean_text(get(r, "symbol", "合约代码", "代码"), "") or "").upper()
            variety = (clean_text(get(r, "variety", "品种"), "") or symbol[:2]).upper()
            if variety not in VARIETIES:
                continue
            trade_date = to_date(get(r, "date", "trade_date", "日期"))
            if trade_date is None or not symbol:
                continue
            rows.append({
                "symbol": symbol,
                "variety": variety,
                "trade_date": trade_date,
                "open": to_float(get(r, "open", "开盘价", "开盘")),
                "high": to_float(get(r, "high", "最高价", "最高")),
                "low": to_float(get(r, "low", "最低价", "最低")),
                "close": to_float(get(r, "close", "收盘价", "收盘")),
                "settle": to_float(get(r, "settle", "结算价")),
                "pre_settle": to_float(get(r, "pre_settle", "前结算价")),
                "volume": to_float(get(r, "volume", "成交量")),
                "oi": to_float(get(r, "open_interest", "持仓量")),
                "turnover": to_float(get(r, "turnover", "成交额")),
            })
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        if not rows:
            return 0
        # 1) Underlying index closes for the same date range (stored by index_daily, adjust="none").
        dates = {r["trade_date"] for r in rows}
        codes = {basis_svc.VARIETY_UNDERLYING[r["variety"]][0] for r in rows if r["variety"] in basis_svc.VARIETY_UNDERLYING}
        spot_map: dict[tuple[str, date], float] = {}
        if codes and dates:
            lo, hi = min(dates), max(dates)
            bars = session.scalars(
                select(DailyQuote).where(
                    DailyQuote.code.in_(list(codes)),
                    DailyQuote.trade_date >= lo,
                    DailyQuote.trade_date <= hi,
                )
            ).all()
            spot_map = {(b.code, b.trade_date): b.close for b in bars if b.close is not None}

        # 2) Link spot + compute basis.
        for r in rows:
            code = basis_svc.VARIETY_UNDERLYING.get(r["variety"], (None, None))[0]
            spot = spot_map.get((code, r["trade_date"])) if code else None
            r["underlying_index"] = code
            r["underlying_index_close"] = spot
            basis, ann, _expiry, _dte = basis_svc.compute_basis(
                r.get("settle") if r.get("settle") is not None else r.get("close"),
                spot,
                r["symbol"],
                r["trade_date"],
            )
            r["basis"] = basis
            r["basis_annualized"] = ann

        codes_done = list({r["symbol"] for r in rows})
        scope = select(IndexFutureDaily).where(IndexFutureDaily.symbol.in_(codes_done))
        return bulk_upsert(
            session, IndexFutureDaily, rows,
            key_fields=["symbol", "trade_date"], scope=scope,
            mutable_fields=[
                "variety", "open", "high", "low", "close", "settle", "pre_settle",
                "volume", "oi", "turnover", "underlying_index", "underlying_index_close",
                "basis", "basis_annualized",
            ],
        )


adapter = IndexFuturesAdapter()
