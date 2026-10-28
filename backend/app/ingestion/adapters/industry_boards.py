"""industry_boards — 行业板块行情 (source 标记为 em, 便于与板块成分区分).

Powers the dashboard 行业热力图 and the sector taxonomy. Per-stock industry membership
is handled by the separate ``industry_constituents`` feed.

Data source: ``stock_fund_flow_industry()`` — 同花顺行业资金流 (即时榜, ~90 行业,
含 行业-涨跌幅/公司家数). Falls back to ``stock_board_industry_name_em()`` if the
primary source is unavailable (requires ``push2.eastmoney.com`` which may be blocked
in some networks). Both frames are read **by column name**, never by position —
an EM frame misread positionally once put 行业指数 点位 (~10000) into change_pct
and the 行业热力图 showed "10000%". ``_sane_change_pct`` is the last-line guard.
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

# 行业板块日涨跌幅的合理上界 — 板块指数是成分股加权, 单日不可能超出该范围;
# 超出几乎必然是上游列错位 (如把 行业指数/最新价 点位 ~几千到几万 当成了涨跌幅).
MAX_SANE_CHANGE_PCT = 30.0


def _sane_change_pct(v: float | None) -> float | None:
    if v is None:
        return None
    if abs(v) > MAX_SANE_CHANGE_PCT:
        logger.warning("[industry_boards] change_pct=%s out of range — dropping (上游列疑似错位)", v)
        return None
    return v


class IndustryBoardsAdapter(BaseAdapter):
    name = "industry_boards"
    description = "东财-行业板块列表与行情"

    def fetch(self, **kwargs) -> Any:
        ak = get_ak()
        # Primary: stock_fund_flow_industry (uses data.10jqka.com.cn, usually reachable).
        # Empty result counts as failure — a drifted layout can parse to nothing.
        try:
            raw = ak.stock_fund_flow_industry()
            if raw is not None and not raw.empty:
                return raw
            logger.warning("[industry_boards] stock_fund_flow_industry returned empty, trying fallback")
        except Exception as exc:
            logger.warning("[industry_boards] stock_fund_flow_industry failed: %s, trying fallback", exc)
        # Fallback: stock_board_industry_name_em (requires push2.eastmoney.com)
        return ak.stock_board_industry_name_em()

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cols = list(raw.columns)

        # Detect source by its exact column signature (column names, not positions).
        is_fund_flow = any("行业-涨跌幅" in str(c) for c in cols)
        if not is_fund_flow and not any("板块名称" in str(c) or "名称" in str(c) for c in cols):
            logger.warning("[industry_boards] unknown frame layout, cols=%s — skipping", cols)
            return rows

        if is_fund_flow:
            # stock_fund_flow_industry (THS 即时): [序号, 行业, 行业指数, 行业-涨跌幅,
            # 流入资金, 流出资金, 净额, 公司家数, 领涨股, 领涨股-涨跌幅, 当前价]
            # — 即时榜没有换手率列, turnover 留空.
            for _, r in raw.iterrows():
                name = clean_text(get(r, "行业"))
                if not name:
                    continue
                rows.append(
                    {
                        "name": name,
                        "code": None,
                        "source": "em",
                        "group": group_of(name),
                        "change_pct": _sane_change_pct(to_float(get(r, "行业-涨跌幅"))),
                        "turnover": None,
                        "company_count": to_int(get(r, "公司家数")),
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
                        "change_pct": _sane_change_pct(to_float(get(r, "涨跌幅"))),
                        "turnover": to_float(get(r, "换手率")),
                        "company_count": (up + down) or None,
                    }
                )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        return bulk_upsert(session, IndustryBoard, rows, key_fields=["name", "source"])


adapter = IndustryBoardsAdapter()
