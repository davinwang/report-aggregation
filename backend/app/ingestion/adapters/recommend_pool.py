"""recommend_pool — bulk 机构推荐池 via ``stock_institute_recommend``.

Fetches the "上调评级股票" / "下调评级股票" pools (whole-market, one call each) and
materializes them as rule-based ``Signal`` rows — the stock analog of the reference's
可操作信号. No LLM involved (AI deferred).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, norm_code, norm_rating, to_date, to_float
from app.ingestion.secmap import industry_group_map, security_id_map
from app.models.base import RatingDirection
from app.models.research import Signal

logger = get_logger(__name__)

POOLS = {"上调评级股票": "upgrade", "下调评级股票": "downgrade"}
_STRENGTH = {RatingDirection.buy: "强", RatingDirection.overweight: "中", RatingDirection.neutral: "弱"}


class RecommendPoolAdapter(BaseAdapter):
    name = "recommend_pool"
    description = "新浪-机构推荐池 (上调/下调评级) → 可操作信号"

    def fetch(self, pools: list[str] | None = None, **kwargs) -> Any:
        ak = get_ak()
        out: list[tuple[str, Any]] = []
        for pool in pools or list(POOLS.keys()):
            throttle.default_throttle.wait()
            try:
                out.append((pool, ak.stock_institute_recommend(symbol=pool)))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[recommend_pool] %s failed: %s", pool, exc)
        return out

    def normalize(self, raw: Any, trade_date: date | None = None, **kwargs) -> list[dict[str, Any]]:
        today = trade_date or date.today()
        rows: list[dict[str, Any]] = []
        for pool, df in raw or []:
            kind = POOLS.get(pool, "rating")
            for r in records(df):
                code = norm_code(get(r, "股票代码", "代码", "证券代码"))
                if not code:
                    continue
                rating = clean_text(get(r, "最新评级", "综合评级", "投资评级"))
                direction = norm_rating(rating)
                d = to_date(get(r, "评级日期", "日期")) or today
                rows.append(
                    {
                        "code": code,
                        "name": clean_text(get(r, "股票名称", "证券简称", "名称")),
                        "trade_date": d,
                        "kind": kind,
                        "direction": direction.value,
                        "strength": _STRENGTH.get(direction, "中"),
                        "score": to_float(get(r, "平均涨幅", "目标价")),
                        "reason": f"{pool}·{rating or '评级'}",
                        "industry_group": clean_text(get(r, "行业")),
                        "sources_json": [{"pool": pool, "rating": rating}],
                    }
                )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        codes = [r["code"] for r in rows]
        id_map = security_id_map(session, codes)
        grp_map = industry_group_map(session, codes)
        for r in rows:
            r["security_id"] = id_map.get(r["code"])
            if not r.get("industry_group"):
                r["industry_group"] = grp_map.get(r["code"])
        dates = {r["trade_date"] for r in rows}
        scope = select(Signal).where(Signal.trade_date.in_(dates))
        return bulk_upsert(session, Signal, rows, key_fields=["code", "trade_date", "kind"], scope=scope)


adapter = RecommendPoolAdapter()
