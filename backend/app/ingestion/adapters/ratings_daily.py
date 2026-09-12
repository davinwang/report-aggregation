"""ratings_daily — whole-market investment ratings for a trading day.

``stock_rank_forecast_cninfo(date=)`` is the KEY bulk feed: one call returns every
rating action published that day (证券代码/研究机构/研究员/投资评级/评级变化/目标价),
which is the stock analog of the reference's per-period 研报 window. Drives 研报库,
可操作信号 and 研报准确率 without per-symbol crawling.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import (
    clean_text,
    norm_code,
    norm_rating,
    rating_change_kind,
    to_date,
    to_float,
)
from app.ingestion.secmap import security_id_map
from app.models.research import RatingEvent


def _date_arg(d: date) -> str:
    return d.strftime("%Y%m%d")


class RatingsDailyAdapter(BaseAdapter):
    name = "ratings_daily"
    description = "巨潮-投资评级 (全市场, 按交易日)"

    def fetch(self, trade_date: date | None = None, **kwargs) -> Any:
        ak = get_ak()
        d = trade_date or date.today()
        return ak.stock_rank_forecast_cninfo(date=_date_arg(d))

    def normalize(self, raw: Any, trade_date: date | None = None, **kwargs) -> list[dict[str, Any]]:
        d = trade_date or date.today()
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            code = norm_code(get(r, "证券代码", "股票代码", "代码"))
            if not code:
                continue
            rating = clean_text(get(r, "投资评级", "最新评级", "评级"))
            prev = clean_text(get(r, "前一次投资评级"))
            change = clean_text(get(r, "评级变化")) or rating_change_kind(prev, rating)
            is_first = str(get(r, "是否首次评级", "")).strip() in ("是", "True", "true", "1", "首次")
            pub = to_date(get(r, "发布日期", "评级日期", "日期")) or d
            rows.append(
                {
                    "code": code,
                    "name": clean_text(get(r, "证券简称", "股票简称", "名称")),
                    "trade_date": pub,
                    "org": clean_text(get(r, "研究机构简称", "机构", "研究机构")),
                    "analyst": clean_text(get(r, "研究员名称", "分析师", "研究员")),
                    "rating": rating,
                    "rating_norm": norm_rating(rating).value,
                    "prev_rating": prev,
                    "rating_change": change,
                    "is_first": is_first,
                    "target_low": to_float(get(r, "目标价格-下限", "目标价下限", "目标价")),
                    "target_high": to_float(get(r, "目标价格-上限", "目标价上限")),
                    "industry": clean_text(get(r, "行业")),
                    "source": "cninfo",
                }
            )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        id_map = security_id_map(session, [r["code"] for r in rows])
        for r in rows:
            r["security_id"] = id_map.get(r["code"])
        dates = {r["trade_date"] for r in rows}
        scope = select(RatingEvent).where(RatingEvent.trade_date.in_(dates))
        return bulk_upsert(
            session, RatingEvent, rows,
            key_fields=["code", "org", "analyst", "trade_date"],
            scope=scope,
        )


adapter = RatingsDailyAdapter()
