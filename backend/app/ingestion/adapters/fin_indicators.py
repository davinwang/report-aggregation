"""fin_indicators — curated key metrics via ``stock_financial_analysis_indicator`` (Sina).

Extracts the handful of ratios/margins needed for fast listing & display (EPS, BPS, ROE,
growth rates, margins, debt ratio, per-share OCF) into ``FinancialIndicator``. Verbose
Chinese column names are matched by substring to survive source drift.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.akshare_client import get_ak
from app.ingestion.base import SymbolLoopAdapter, bulk_upsert
from app.ingestion.df_utils import get, get_contains, records
from app.ingestion.normalizers import norm_code, to_float, to_period_str
from app.ingestion.secmap import security_id_map
from app.models.financial import FinancialIndicator

# field -> column-name substrings (first match wins)
_FIELDS: dict[str, tuple[str, ...]] = {
    "eps": ("摊薄每股收益", "每股收益"),
    "bps": ("每股净资产_调整后", "每股净资产"),
    "roe": ("净资产收益率", "加权净资产收益率"),
    "roa": ("总资产净利率", "总资产利润率"),
    "revenue_yoy": ("主营业务收入增长率", "营业总收入同比", "营业收入同比"),
    "net_profit_yoy": ("净利润增长率", "净利润同比"),
    "gross_margin": ("销售毛利率", "毛利率"),
    "net_margin": ("销售净利率", "净利率"),
    "debt_ratio": ("资产负债率",),
    "ocfps": ("每股经营性现金流", "每股经营现金流"),
}


class FinIndicatorsAdapter(SymbolLoopAdapter):
    name = "fin_indicators"
    description = "新浪-财务分析指标 (EPS/ROE/毛利率/负债率等, 按universe)"

    def fetch_symbol(self, code: str, start_year: str | None = None, **kwargs) -> Any:
        ak = get_ak()
        sy = start_year or str(date.today().year - 5)
        return ak.stock_financial_analysis_indicator(symbol=norm_code(code), start_year=sy)

    def normalize_symbol(self, code: str, raw: Any, max_periods: int = 16, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for r in records(raw)[:max_periods]:
            period = to_period_str(get(r, "日期", "报告期"))
            if not period:
                continue
            rec: dict[str, Any] = {
                "code": norm_code(code),
                "report_period": period,
            }
            for field, subs in _FIELDS.items():
                rec[field] = to_float(get_contains(r, *subs))
            rows.append(rec)
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        id_map = security_id_map(session, [r["code"] for r in rows])
        for r in rows:
            r["security_id"] = id_map.get(r["code"])
        codes = list({r["code"] for r in rows})
        scope = select(FinancialIndicator).where(FinancialIndicator.code.in_(codes))
        return bulk_upsert(session, FinancialIndicator, rows,
                           key_fields=["code", "report_period"], scope=scope)


adapter = FinIndicatorsAdapter()
