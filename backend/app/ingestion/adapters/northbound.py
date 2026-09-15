"""northbound — 沪深港通资金流向 (``stock_hsgt_fund_flow_summary_em``).

The frame has 4 rows per session — 沪股通/深股通 (北向) and 港股通(沪)/港股通(深) (南向) —
carrying 资金净流入, 成交净买额, 当日资金余额 plus **market breadth** (上涨/持平/下跌家数)
and the related index move.

Note: mainland-leg (北向) net-flow disclosure has been suspended by the exchanges, so
``资金净流入``/``成交净买额`` come back as 0 for 沪股通/深股通; the breadth counters remain
live, which is why they are preserved in ``extra_json``.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_date, to_float, to_int
from app.models.flow import NorthboundDaily


class NorthboundAdapter(BaseAdapter):
    name = "northbound"
    description = "沪深港通资金流向 + 涨跌家数 (沪股通/深股通/港股通)"

    def fetch(self, **kwargs) -> Any:
        return get_ak().stock_hsgt_fund_flow_summary_em()

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            trade_date = to_date(get(r, "交易日", "日期"))
            board = clean_text(get(r, "板块", "类型"), "")
            if trade_date is None or not board:
                continue
            rows.append({
                "trade_date": trade_date,
                "board": board,
                "net_inflow": to_float(get(r, "资金净流入")),
                "extra_json": {
                    "type": clean_text(get(r, "类型")),
                    "direction": clean_text(get(r, "资金方向")),
                    "status": to_int(get(r, "交易状态")),
                    "net_buy": to_float(get(r, "成交净买额")),
                    "balance": to_float(get(r, "当日资金余额")),
                    "up": to_int(get(r, "上涨数")),
                    "flat": to_int(get(r, "持平数")),
                    "down": to_int(get(r, "下跌数")),
                    "index": clean_text(get(r, "相关指数")),
                    "index_pct": to_float(get(r, "指数涨跌幅")),
                },
            })
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        dates = list({r["trade_date"] for r in rows})
        scope = select(NorthboundDaily).where(NorthboundDaily.trade_date.in_(dates))
        return bulk_upsert(
            session, NorthboundDaily, rows,
            key_fields=["trade_date", "board"], scope=scope,
            mutable_fields=["net_inflow", "extra_json"],
        )


adapter = NorthboundAdapter()
