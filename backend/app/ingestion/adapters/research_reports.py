"""research_reports — per-symbol 个股研报 via ``stock_research_report_em``.

Returns each stock's full research-report history from 东财 (报告名称/东财评级/机构/
盈利预测/行业/日期/PDF链接). Restricted to a universe; powers the 研报库 detail rows
(titles + PDF links) that the bulk ratings feed does not carry.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import SymbolLoopAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_date, to_float, to_int
from app.ingestion.secmap import industry_group_map, security_id_map
from app.models.research import ResearchReport

_FORECAST_RE = re.compile(r"^(\d{4})-盈利预测-(收益|市盈率)$")


def _extract_forecast(r: dict) -> dict:
    out: dict[str, dict[str, float]] = {}
    for k, v in r.items():
        m = _FORECAST_RE.match(str(k))
        if not m:
            continue
        year, metric = m.group(1), m.group(2)
        val = to_float(v)
        if val is None:
            continue
        out.setdefault(year, {})["eps" if metric == "收益" else "pe"] = val
    return out


class ResearchReportsAdapter(SymbolLoopAdapter):
    name = "research_reports"
    description = "东财-个股研报 (标题/评级/盈利预测/PDF, 按universe)"

    def fetch_symbol(self, code: str, **kwargs) -> Any:
        ak = get_ak()
        return ak.stock_research_report_em(symbol=code)

    def normalize_symbol(self, code: str, raw: Any, since_days: int | None = None, **kwargs) -> list[dict[str, Any]]:
        cutoff = date.today().toordinal() - since_days if since_days else None
        rows: list[dict[str, Any]] = []
        for r in records(raw):
            title = clean_text(get(r, "报告名称", "标题"))
            pub = to_date(get(r, "日期", "发布日期"))
            if not title or pub is None:
                continue
            if cutoff and pub.toordinal() < cutoff:
                continue
            rating = clean_text(get(r, "东财评级", "评级"))
            rows.append(
                {
                    "code": code,
                    "name": clean_text(get(r, "股票简称", "名称")),
                    "title": title[:500],
                    "org": clean_text(get(r, "机构")),
                    "analysts": None,
                    "rating": rating,
                    "rating_change": None,
                    "industry": clean_text(get(r, "行业")),
                    "publish_date": pub,
                    "report_count_1m": to_int(get(r, "近一月个股研报数")),
                    "pdf_url": clean_text(get(r, "报告PDF链接", "PDF链接")),
                    "forecast_json": _extract_forecast(r) or None,
                    "source": "em",
                    "ingested_at": date.today(),
                }
            )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        id_map = security_id_map(session, [r["code"] for r in rows])
        grp_map = industry_group_map(session, [r["code"] for r in rows])
        for r in rows:
            r["security_id"] = id_map.get(r["code"])
            if not r.get("industry_group"):
                r["industry_group"] = grp_map.get(r["code"]) or r.get("industry")
        codes = list({r["code"] for r in rows})
        scope = select(ResearchReport).where(ResearchReport.code.in_(codes))
        return bulk_upsert(
            session, ResearchReport, rows,
            key_fields=["code", "title", "org", "publish_date"],
            scope=scope,
        )


adapter = ResearchReportsAdapter()
