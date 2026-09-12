"""earnings — 业绩报表 via ``stock_yjbb_em(date=)`` (东财, bulk per quarter).

One call returns the whole market's reported performance for a quarter — a cheap way
to populate headline financials (revenue/profit + YoY, EPS, ROE, margin) for screening.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, norm_code, to_date, to_float
from app.models.financial import EarningsReport


def latest_quarter(today: date | None = None) -> str:
    """Most recent likely-reported quarter end as YYYYMMDD."""
    t = today or date.today()
    q_ends = [(3, 31), (6, 30), (9, 30), (12, 31)]
    year = t.year
    candidates = [f"{year}{m:02d}{d:02d}" for m, d in q_ends]
    past = [c for c in candidates if c <= t.strftime("%Y%m%d")]
    if past:
        return past[-1]
    return f"{year - 1}1231"


class EarningsAdapter(BaseAdapter):
    name = "earnings"
    description = "东财-业绩报表 (全市场季度业绩)"

    def fetch(self, quarter: str | None = None, **kwargs) -> Any:
        ak = get_ak()
        return ak.stock_yjbb_em(date=quarter or latest_quarter())

    def normalize(self, raw: Any, quarter: str | None = None, **kwargs) -> list[dict[str, Any]]:
        period = quarter or latest_quarter()
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            code = norm_code(get(r, "股票代码", "代码"))
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "name": clean_text(get(r, "股票简称", "名称")),
                    "report_period": period,
                    "revenue": to_float(get(r, "营业收入-营业收入", "营业收入")),
                    "revenue_yoy": to_float(get(r, "营业收入-同比增长")),
                    "net_profit": to_float(get(r, "净利润-净利润", "净利润")),
                    "net_profit_yoy": to_float(get(r, "净利润-同比增长")),
                    "eps": to_float(get(r, "每股收益")),
                    "roe": to_float(get(r, "净资产收益率")),
                    "gross_margin": to_float(get(r, "销售毛利率")),
                    "disclose_date": to_date(get(r, "最新公告日期", "公告日期")),
                }
            )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        period = rows[0]["report_period"] if rows else None
        scope = select(EarningsReport).where(EarningsReport.report_period == period) if period else None
        return bulk_upsert(session, EarningsReport, rows, key_fields=["code", "report_period"], scope=scope)


adapter = EarningsAdapter()
