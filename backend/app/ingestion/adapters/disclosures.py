"""disclosures — 公告披露 via ``stock_notice_report`` (东财, bulk by date).

A single call returns the whole market's announcements for one date (title, type,
URL, per-stock code). Looping a recent date window therefore populates per-stock
announcement histories for *all* A-shares — the primary-source complement to the
structured statements, and far broader than a universe-bounded per-symbol crawl.

Note: the legacy per-symbol ``stock_zh_a_disclosure_report_cninfo`` interface is
currently unusable — its internal ``__get_stock_json`` helper now receives non-JSON
from cninfo (``JSONDecodeError``), so it is intentionally not used here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, norm_code, to_date
from app.models.financial import Disclosure

logger = get_logger(__name__)

_ALL = "全部"  # category: every announcement type
_DEFAULT_DAYS = 45  # default backfill window (calendar days)


class DisclosuresAdapter(BaseAdapter):
    name = "disclosures"
    description = "东财-公告披露 (标题/类型/链接, 全市场按日期)"
    per_symbol = False

    def _dates(self, start: str | None, end: str | None) -> list[str]:
        """Expand a YYYYMMDD window into per-day strings (weekends included — the
        upstream simply returns nothing for non-trading days)."""
        if start:
            start_d = datetime.strptime(start, "%Y%m%d").date()
            end_d = datetime.strptime(end, "%Y%m%d").date() if end else date.today()
        else:
            end_d = datetime.strptime(end, "%Y%m%d").date() if end else date.today()
            start_d = end_d - timedelta(days=_DEFAULT_DAYS)
        days: list[str] = []
        d = start_d
        while d <= end_d:
            days.append(d.strftime("%Y%m%d"))
            d += timedelta(days=1)
        return days

    def fetch(self, start: str | None = None, end: str | None = None, **kwargs) -> list[Any]:
        ak = get_ak()
        frames: list[Any] = []
        for day in self._dates(start, end):
            try:
                frames.append(ak.stock_notice_report(symbol=_ALL, date=day))
            except Exception as exc:  # noqa: BLE001 - a bad day must not abort the window
                logger.debug("[%s] %s returned no data: %s", self.name, day, exc)
        return frames

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[tuple] = set()
        for frame in raw or []:
            for r in records(frame):
                code = norm_code(get(r, "代码"))
                title = clean_text(get(r, "公告标题", "标题"))
                d = to_date(get(r, "公告日期", "日期"))
                if not code or not title or d is None:
                    continue
                key = (code, d, title)
                if key in seen:  # intra-batch duplicate (same announcement on a page)
                    continue
                seen.add(key)
                rows.append(
                    {
                        "code": code,
                        "name": clean_text(get(r, "名称", "简称")),
                        "ann_date": d,
                        "title": title[:500],
                        "category": clean_text(get(r, "公告类型", "类型")),
                        "url": clean_text(get(r, "网址", "链接")),
                        "source": "em",
                    }
                )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        if not rows:
            return 0
        dates = [r["ann_date"] for r in rows if r.get("ann_date")]
        scope = (
            select(Disclosure).where(Disclosure.ann_date >= min(dates), Disclosure.ann_date <= max(dates))
            if dates
            else None
        )
        return bulk_upsert(
            session, Disclosure, rows,
            key_fields=["code", "ann_date", "title"],
            scope=scope,
        )


adapter = DisclosuresAdapter()
