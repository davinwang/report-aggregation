"""industry_constituents — map each stock to its 东财 industry board.

Self-contained: fetches the board list, then each board's constituents, updating both
``IndustryConstituent`` and ``Security.industry_sw``/``industry_group``. This is the
cheapest whole-market way to classify stocks by sector (~87 calls) vs. per-stock lookups.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, norm_code
from app.models.security import IndustryConstituent, Security, group_of

logger = get_logger(__name__)


class IndustryConstituentsAdapter(BaseAdapter):
    name = "industry_constituents"
    description = "东财-行业板块成分 (为个股标注所属行业)"

    def fetch(self, max_boards: int | None = None, **kwargs) -> Any:
        ak = get_ak()
        throttle.default_throttle.wait()
        boards_df = ak.stock_board_industry_name_em()
        names = [clean_text(get(r, "板块名称", "名称")) for r in records(boards_df)]
        names = [n for n in names if n]
        if max_boards:
            names = names[:max_boards]
        out: list[tuple[str, Any]] = []
        for nm in names:
            throttle.default_throttle.wait()
            try:
                out.append((nm, ak.stock_board_industry_cons_em(symbol=nm)))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[industry_constituents] %s failed: %s", nm, exc)
        return out

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for board, df in raw or []:
            for r in records(df):
                code = norm_code(get(r, "代码", "股票代码"))
                if not code:
                    continue
                rows.append({
                    "board_name": board,
                    "code": code,
                    "name": clean_text(get(r, "名称", "股票名称")),
                })
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        n = bulk_upsert(session, IndustryConstituent, rows, key_fields=["board_name", "code"])
        # Assign each stock its (last-seen) industry board.
        code_to_board: dict[str, str] = {}
        for r in rows:
            code_to_board[r["code"]] = r["board_name"]
        codes = list(code_to_board.keys())
        updated = 0
        for i in range(0, len(codes), 800):
            chunk = codes[i : i + 800]
            for sec in session.scalars(select(Security).where(Security.code.in_(chunk))).all():
                board = code_to_board.get(sec.code)
                if board and sec.industry_sw != board:
                    sec.industry_sw = board
                    sec.industry_group = group_of(board)
                    updated += 1
                elif board and not sec.industry_sw:
                    sec.industry_sw = board
                    sec.industry_group = group_of(board)
                    updated += 1
        session.flush()
        logger.info("[industry_constituents] classified %d securities", updated)
        return n


adapter = IndustryConstituentsAdapter()
