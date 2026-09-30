"""lhb — 龙虎榜 (``stock_lhb_detail_em``), the daily top-list of abnormal trading.

One row per (security, trade date, 上榜原因); a stock can appear several times a day
for different reasons, which is exactly the model's unique key.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, norm_code, to_date, to_float
from app.models.flow import LhbRecord

DEFAULT_DAYS = 10


def _parse_ymd(s: Any) -> date | None:
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


class LhbAdapter(BaseAdapter):
    name = "lhb"
    description = "龙虎榜每日明细 (净买额/买卖额/上榜原因)"

    def fetch(self, start: Any = None, end: Any = None, days: int = DEFAULT_DAYS, **kwargs) -> Any:
        ak = get_ak()
        end_d = _parse_ymd(end) or date.today()
        start_d = _parse_ymd(start) or (end_d - timedelta(days=max(1, days)))
        return ak.stock_lhb_detail_em(
            start_date=start_d.strftime("%Y%m%d"), end_date=end_d.strftime("%Y%m%d")
        )

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            code = norm_code(get(r, "代码"))
            trade_date = to_date(get(r, "上榜日", "日期"))
            if not code or trade_date is None:
                continue
            rows.append({
                "code": code,
                "name": clean_text(get(r, "名称")),
                "trade_date": trade_date,
                "reason": clean_text(get(r, "上榜原因")),
                "close": to_float(get(r, "收盘价")),
                "change_pct": to_float(get(r, "涨跌幅")),
                "buy_amt": to_float(get(r, "龙虎榜买入额")),
                "sell_amt": to_float(get(r, "龙虎榜卖出额")),
                "net_amt": to_float(get(r, "龙虎榜净买额")),
                "turnover": to_float(get(r, "换手率")),
            })
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        dates = list({r["trade_date"] for r in rows})
        scope = select(LhbRecord).where(LhbRecord.trade_date.in_(dates))
        return bulk_upsert(
            session, LhbRecord, rows,
            key_fields=["code", "trade_date", "reason"], scope=scope,
            mutable_fields=[
                "name", "close", "change_pct", "buy_amt", "sell_amt", "net_amt", "turnover",
            ],
        )


adapter = LhbAdapter()
