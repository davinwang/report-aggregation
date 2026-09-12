"""spot_snapshot — whole-market daily snapshot via ``stock_zh_a_spot_em`` (one call).

Stored as DailyQuote rows with ``adjust="raw"`` for the current trading day. Cheap and
whole-market, so it powers the dashboard's latest-price/change/turnover without any
per-symbol crawling.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import norm_code, to_float
from app.ingestion.secmap import security_id_map
from app.models.market import DailyQuote


class SpotSnapshotAdapter(BaseAdapter):
    name = "spot_snapshot"
    description = "沪深京A股实时/收盘快照 (全市场, 单次调用)"

    def fetch(self, **kwargs) -> Any:
        ak = get_ak()
        return ak.stock_zh_a_spot_em()

    def normalize(self, raw: Any, trade_date: date | None = None, **kwargs) -> list[dict[str, Any]]:
        d = trade_date or date.today()
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            code = norm_code(get(r, "代码", "code"))
            close = to_float(get(r, "最新价", "收盘", "close"))
            if not code or close is None:
                continue
            rows.append(
                {
                    "code": code,
                    "trade_date": d,
                    "open": to_float(get(r, "今开", "开盘")),
                    "high": to_float(get(r, "最高")),
                    "low": to_float(get(r, "最低")),
                    "close": close,
                    "pre_close": to_float(get(r, "昨收")),
                    "volume": to_float(get(r, "成交量")),
                    "amount": to_float(get(r, "成交额")),
                    "turnover_rate": to_float(get(r, "换手率")),
                    "change_pct": to_float(get(r, "涨跌幅")),
                    "adjust": "raw",
                    "source": "em",
                }
            )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        id_map = security_id_map(session, [r["code"] for r in rows])
        for r in rows:
            r["security_id"] = id_map.get(r["code"])
        d = rows[0]["trade_date"]
        scope = select(DailyQuote).where(DailyQuote.trade_date == d, DailyQuote.adjust == "raw")
        return bulk_upsert(
            session, DailyQuote, rows,
            key_fields=["code", "trade_date", "adjust"],
            scope=scope,
        )


adapter = SpotSnapshotAdapter()
