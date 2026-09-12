"""price_history — per-symbol daily bars via ``stock_zh_a_hist`` (前复权).

Backfills/refreshes K-line history for a universe. Default window is the last
``DEFAULT_YEARS`` years; the pipeline can pass explicit ``start``/``end``.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import SymbolLoopAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import to_date, to_float
from app.ingestion.secmap import security_id_map
from app.models.market import DailyQuote

DEFAULT_YEARS = 3


class PriceHistoryAdapter(SymbolLoopAdapter):
    name = "price_history"
    description = "个股日线历史行情 (前复权, 按universe)"

    def fetch_symbol(self, code: str, start: str | None = None, end: str | None = None,
                     adjust: str = "qfq", **kwargs) -> Any:
        ak = get_ak()
        end_d = end or date.today().strftime("%Y%m%d")
        start_d = start or (date.today() - timedelta(days=365 * DEFAULT_YEARS)).strftime("%Y%m%d")
        return ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_d, end_date=end_d, adjust=adjust)

    def normalize_symbol(self, code: str, raw: Any, adjust: str = "qfq", **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            d = to_date(get(r, "日期", "date"))
            close = to_float(get(r, "收盘", "close"))
            if d is None or close is None:
                continue
            rows.append(
                {
                    "code": code,
                    "trade_date": d,
                    "open": to_float(get(r, "开盘", "open")),
                    "high": to_float(get(r, "最高", "high")),
                    "low": to_float(get(r, "最低", "low")),
                    "close": close,
                    "volume": to_float(get(r, "成交量", "volume")),
                    "amount": to_float(get(r, "成交额", "amount")),
                    "turnover_rate": to_float(get(r, "换手率")),
                    "change_pct": to_float(get(r, "涨跌幅")),
                    "adjust": adjust,
                    "source": "em",
                }
            )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        id_map = security_id_map(session, [r["code"] for r in rows])
        for r in rows:
            r["security_id"] = id_map.get(r["code"])
        codes = list({r["code"] for r in rows})
        adjust = rows[0]["adjust"] if rows else "qfq"
        scope = select(DailyQuote).where(DailyQuote.code.in_(codes), DailyQuote.adjust == adjust)
        return bulk_upsert(session, DailyQuote, rows, key_fields=["code", "trade_date", "adjust"], scope=scope)


adapter = PriceHistoryAdapter()
