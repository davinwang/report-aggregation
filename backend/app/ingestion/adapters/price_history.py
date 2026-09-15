"""price_history — per-symbol daily bars with a source fallback chain.

Sources (first non-empty wins, per symbol):
1. ``stock_zh_a_hist`` (东方财富) — richest frame (换手率/涨跌幅);
2. ``stock_zh_a_daily`` (新浪, sh600519 format) — used when 东财 throttles;
3. ``stock_zh_a_hist_tx`` (腾讯) — last resort.

Default window is the last ``DEFAULT_YEARS`` years; the pipeline can pass explicit
``start``/``end``. Volume units differ per source (东财=手, 新浪/腾讯=股); close
prices are 前复权 across sources, which is what downstream returns need.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import SymbolLoopAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import sina_symbol, to_date, to_float
from app.ingestion.secmap import security_id_map
from app.models.market import DailyQuote

DEFAULT_YEARS = 3


def _source_of(raw: Any) -> str:
    """Detect the upstream source from the frame's columns."""
    cols = {str(c) for c in raw.columns}
    if "日期" in cols:
        return "em"
    if "outstanding_share" in cols:
        return "sina"
    return "tx"


class PriceHistoryAdapter(SymbolLoopAdapter):
    name = "price_history"
    description = "个股日线历史行情 (前复权, 按universe; 东财→新浪→腾讯回退)"

    def fetch_symbol(self, code: str, start: str | None = None, end: str | None = None,
                     adjust: str = "qfq", **kwargs) -> Any:
        ak = get_ak()
        end_d = end or date.today().strftime("%Y%m%d")
        start_d = start or (date.today() - timedelta(days=365 * DEFAULT_YEARS)).strftime("%Y%m%d")
        sym = sina_symbol(code)
        chain = (
            ("em", lambda: ak.stock_zh_a_hist(symbol=code, period="daily",
                                              start_date=start_d, end_date=end_d, adjust=adjust)),
            ("sina", lambda: ak.stock_zh_a_daily(symbol=sym, start_date=start_d,
                                                 end_date=end_d, adjust=adjust)),
            ("tx", lambda: ak.stock_zh_a_hist_tx(symbol=sym, start_date=start_d,
                                                 end_date=end_d, adjust=adjust)),
        )
        errors: list[str] = []
        for source, call in chain:
            try:
                df = call()
                if df is not None and len(df) > 0:
                    return df
                errors.append(f"{source}: empty")
            except Exception as exc:  # noqa: BLE001 - try the next source
                errors.append(f"{source}: {type(exc).__name__}")
        raise RuntimeError(f"all price sources failed for {code}: " + ", ".join(errors))

    def normalize_symbol(self, code: str, raw: Any, adjust: str = "qfq", **kwargs) -> list[dict[str, Any]]:
        source = _source_of(raw)
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
                    "source": source,
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
