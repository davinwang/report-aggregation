"""industry_boards — 东财行业板块行情 via ``stock_board_industry_name_em`` (one call).

Powers the dashboard 行业热力图 and the sector taxonomy. Per-stock industry membership
is handled by the separate ``industry_constituents`` feed.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_float, to_int
from app.models.security import IndustryBoard, group_of


class IndustryBoardsAdapter(BaseAdapter):
    name = "industry_boards"
    description = "东财-行业板块列表与行情"

    def fetch(self, **kwargs) -> Any:
        ak = get_ak()
        return ak.stock_board_industry_name_em()

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
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
