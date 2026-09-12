"""disclosures — 公告披露 via ``stock_zh_a_disclosure_report_cninfo`` (巨潮, per symbol).

Provides announcement titles + original PDF links (财报/重大事项/…) for a universe,
complementing the structured financial statements with primary-source documents.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import SymbolLoopAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, norm_code, to_date
from app.models.financial import Disclosure

_CNINFO_STATIC = "http://static.cninfo.com.cn/"


def _full_url(u: str | None) -> str | None:
    u = clean_text(u)
    if not u:
        return None
    if u.startswith("http"):
        return u
    return _CNINFO_STATIC + u.lstrip("/")


class DisclosuresAdapter(SymbolLoopAdapter):
    name = "disclosures"
    description = "巨潮-公告披露 (标题/PDF链接, 按universe)"

    def fetch_symbol(self, code: str, start: str | None = None, end: str | None = None, **kwargs) -> Any:
        ak = get_ak()
        end_d = end or date.today().strftime("%Y%m%d")
        start_d = start or (date.today() - timedelta(days=365)).strftime("%Y%m%d")
        return ak.stock_zh_a_disclosure_report_cninfo(
            symbol=norm_code(code), market="沪深京", category="", start_date=start_d, end_date=end_d
        )

    def normalize_symbol(self, code: str, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            title = clean_text(get(r, "公告标题", "标题"))
            d = to_date(get(r, "公告日期", "日期", "发布时间"))
            if not title or d is None:
                continue
            rows.append(
                {
                    "code": norm_code(get(r, "代码", default=code)) or code,
                    "name": clean_text(get(r, "简称", "名称")),
                    "ann_date": d,
                    "title": title[:500],
                    "category": clean_text(get(r, "公告类型", "类型")),
                    "url": _full_url(get(r, "附件链接", "链接", "公告链接")),
                    "source": "cninfo",
                }
            )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        codes = list({r["code"] for r in rows})
        scope = select(Disclosure).where(Disclosure.code.in_(codes))
        return bulk_upsert(
            session, Disclosure, rows,
            key_fields=["code", "ann_date", "title"],
            scope=scope,
        )


adapter = DisclosuresAdapter()
