"""industry_boards — 东财行业板块行情.

Powers the dashboard 行业热力图 and the sector taxonomy. Per-stock industry membership
is handled by the separate ``industry_constituents`` feed.

Data source: ``stock_fund_flow_industry()`` (90 申万行业, includes change %, turnover,
company count). Falls back to ``stock_board_industry_name_em()`` if the primary source
is unavailable (requires ``push2.eastmoney.com`` which may be blocked in some networks).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_float, to_int
from app.models.security import IndustryBoard, group_of

logger = get_logger(__name__)


class IndustryBoardsAdapter(BaseAdapter):
    name = "industry_boards"
    description = "东财-行业板块列表与行情"

    def fetch(self, **kwargs) -> Any:
        ak = get_ak()
        # Primary: stock_fund_flow_industry (uses datacenter-web, usually reachable)
        try:
            return ak.stock_fund_flow_industry()
        except Exception as exc:
            logger.warning("[industry_boards] stock_fund_flow_industry failed: %s, trying fallback", exc)
            # Fallback: stock_board_industry_name_em (requires push2.eastmoney.com)
            return ak.stock_board_industry_name_em()

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cols = list(raw.columns)

        # Detect source by column names (stock_fund_flow_industry vs stock_board_industry_name_em)
        is_fund_flow = any("行业" in str(c) or "行业" in str(c) for c in cols) or len(cols) >= 10

        if is_fund_flow and len(cols) >= 8:
            # stock_fund_flow_industry: use iloc for encoding-safe access
            # col layout: [序号, 行业, 行业指数, 行业-涨跌幅, 主力流入, 主力流出,
            #              换手, 公司数量, 领涨股, 领涨股-涨跌幅, 换手率]
            for _, r in raw.iterrows():
                name = clean_text(str(r.iloc[1])) if len(r) > 1 else None
                if not name:
                    continue
                rows.append(
                    {
                        "name": name,
                        "code": None,
                        "source": "em",
                        "group": group_of(name),
                        "change_pct": to_float(r.iloc[3]) if len(r) > 3 else None,
                        "turnover": to_float(r.iloc[10]) if len(r) > 10 else to_float(r.iloc[6]),
                        "company_count": to_int(r.iloc[7]) if len(r) > 7 else None,
                    }
                )
        else:
            # Fallback: stock_board_industry_name_em format
            for r in records(raw):
                name = clean_text(get(r, "板块名称", "名称"))
                if not name:
                    continue
                up = to_int(get(r, "上涨家数"), 0) or 0
                down = to_int(get(r, "下跌家数"), 0) or 0
                rows.append(
                    {
                        "name": name,
                        "code": clean_text(get(r, "板块代码", "代码")),
                        "source": "em",
                        "group": group_of(name),
                        "change_pct": to_float(get(r, "涨跌幅")),
                        "turnover": to_float(get(r, "换手率")),
                        "company_count": (up + down) or None,
                    }
                )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        return bulk_upsert(session, IndustryBoard, rows, key_fields=["name", "source"])


adapter = IndustryBoardsAdapter()
