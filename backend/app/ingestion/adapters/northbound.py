"""northbound — 沪深港通资金流向 (``stock_hsgt_fund_flow_summary_em``).

The frame has 4 rows per session — 沪股通/深股通 (北向) and 港股通(沪)/港股通(深) (南向) —
carrying 资金净流入, 成交净买额, 当日资金余额 plus **market breadth** (上涨/持平/下跌家数)
and the related index move.

Note: mainland-leg (北向) net-flow disclosure has been suspended by the exchanges, so
``资金净流入``/``成交净买额`` come back as 0 for 沪股通/深股通; the breadth counters remain
live, which is why they are preserved in ``extra_json``.

The upstream report only ever carries the *current* session and, once the evening
clearing finishes (~16:30 CST), it flips to the next session's placeholder row (all
stocks 持平, 上涨/下跌 = 0) — the closing breadth is gone from that point on. The feed
is therefore scheduled intraday: every 10-minute run keeps the row fresh during the
session and the post-close runs (15:10-15:50) persist the frozen closing counts, well
before the evening rollover. Placeholder rows are dropped in ``normalize`` so they can
neither shadow a real session nor add all-flat junk points to the 涨跌家数 trend.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_date, to_float, to_int
from app.models.flow import NorthboundDaily

logger = get_logger(__name__)


class NorthboundAdapter(BaseAdapter):
    name = "northbound"
    description = "沪深港通资金流向 + 涨跌家数 (沪股通/深股通/港股通)"

    def fetch(self, **kwargs) -> Any:
        return get_ak().stock_hsgt_fund_flow_summary_em()

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        placeholders = 0
        for r in records(raw):
            trade_date = to_date(get(r, "交易日", "日期"))
            board = clean_text(get(r, "板块", "类型"), "")
            if trade_date is None or not board:
                continue
            up = to_int(get(r, "上涨数"))
            down = to_int(get(r, "下跌数"))
            # Pre-open placeholder row (upstream pre-creates the next session with
            # everything 持平): no trade has moved yet, so upserting it would flip
            # the current session's row to all-flat zeros. Wait for live counts.
            if not up and not down:
                placeholders += 1
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
                    "up": up,
                    "flat": to_int(get(r, "持平数")),
                    "down": down,
                    "index": clean_text(get(r, "相关指数")),
                    "index_pct": to_float(get(r, "指数涨跌幅")),
                },
            })
        if placeholders and not rows:
            logger.debug("[northbound] upstream session not open yet (%d placeholder rows); nothing stored",
                         placeholders)
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
