"""stock_flow — per-symbol 个股资金流 via ``stock_individual_fund_flow`` (东财).

Returns each stock's daily 主力/超大单/大单/中单/小单 net-inflow history so the
个股详情 flow panel (``GET /api/stock/{code}/flow``) reads real rows instead of an
always-empty table. Restricted to the universe and a recent window (the UI shows
at most 120 sessions).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import SymbolLoopAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import exchange_of, to_date, to_float
from app.models.flow import FundFlowDaily

DEFAULT_DAYS = 400  # ~1.5 years of sessions; plenty for the ≤120-row panel

_MARKET_OF = {"SSE": "sh", "SZSE": "sz", "BSE": "bj"}


class StockFlowAdapter(SymbolLoopAdapter):
    name = "stock_flow"
    description = "东财-个股资金流 (主力/超大单净流入, 按universe)"

    def fetch_symbol(self, code: str, **kwargs) -> Any:
        ak = get_ak()
        market = _MARKET_OF.get(exchange_of(code), "sh")
        return ak.stock_individual_fund_flow(stock=code, market=market)

    def normalize_symbol(
        self, code: str, raw: Any, since_days: int | None = None, **kwargs,
    ) -> list[dict[str, Any]]:
        days = since_days if since_days is not None else DEFAULT_DAYS
        cutoff = date.today() - timedelta(days=max(1, days))
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            d = to_date(get(r, "日期", "日期(YYYY-MM-DD)", "date"))
            if d is None or d < cutoff:
                continue
            rows.append(
                {
                    "code": code,
                    "trade_date": d,
                    "close": to_float(get(r, "收盘价")),
                    "change_pct": to_float(get(r, "涨跌幅")),
                    "main_net_inflow": to_float(get(r, "主力净流入-净额")),
                    "main_net_inflow_pct": to_float(get(r, "主力净流入-净占比")),
                    "super_large_net": to_float(get(r, "超大单净流入-净额")),
                    "large_net": to_float(get(r, "大单净流入-净额")),
                    "medium_net": to_float(get(r, "中单净流入-净额")),
                    "small_net": to_float(get(r, "小单净流入-净额")),
                }
            )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        codes = list({r["code"] for r in rows})
        scope = select(FundFlowDaily).where(FundFlowDaily.code.in_(codes))
        return bulk_upsert(
            session, FundFlowDaily, rows,
            key_fields=["code", "trade_date"], scope=scope,
        )


adapter = StockFlowAdapter()
