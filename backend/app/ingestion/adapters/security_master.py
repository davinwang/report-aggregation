"""security_master — build the Security table from ``stock_info_a_code_name``.

Bulk, cheap, and the prerequisite for every per-symbol feed (code → security_id).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import exchange_of, norm_code
from app.models.security import Security


class SecurityMasterAdapter(BaseAdapter):
    name = "security_master"
    description = "A股证券主表 (代码/名称/交易所)"

    def fetch(self, **kwargs) -> Any:
        ak = get_ak()
        return ak.stock_info_a_code_name()

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            code = norm_code(get(r, "code", "代码", "证券代码"))
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "name": (get(r, "name", "名称", "证券简称", "股票简称") or "").strip(),
                    "type": "stock",
                    "exchange": exchange_of(code),
                    "is_active": True,
                }
            )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        # Preserve existing industry fields (not returned by this feed).
        return bulk_upsert(
            session,
            Security,
            rows,
            key_fields=["code"],
            mutable_fields=["name", "exchange", "is_active"],
        )

    def latest_date(self, rows):  # no date dimension
        return None


adapter = SecurityMasterAdapter()
