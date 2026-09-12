"""financials_em — 三大报表 via 东财 by-report interfaces (per symbol).

``stock_balance_sheet_by_report_em`` / ``stock_profit_sheet_by_report_em`` /
``stock_cash_flow_sheet_by_report_em`` each return 300+ fields per report period.
We store the raw field map as JSON (bounded to the most recent ``max_periods``) and
rely on ``fin_indicators`` for the curated fast-display metrics.
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion import throttle
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import SymbolLoopAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import em_symbol, to_period_str
from app.ingestion.secmap import security_id_map
from app.models.financial import FinancialStatement

_STATEMENTS = {
    "balance": "stock_balance_sheet_by_report_em",
    "income": "stock_profit_sheet_by_report_em",
    "cashflow": "stock_cash_flow_sheet_by_report_em",
}


def _clean(v: Any) -> Any:
    """Make a value JSON-serializable (NaN/NaT/Timestamp → None/str)."""
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if v is None:
        return None
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


class FinancialsEmAdapter(SymbolLoopAdapter):
    name = "financials_em"
    description = "东财-三大报表 (资产负债/利润/现金流, 按universe)"

    def fetch_symbol(self, code: str, **kwargs) -> Any:
        ak = get_ak()
        sym = em_symbol(code)
        out: dict[str, Any] = {}
        for i, (stmt, fn_name) in enumerate(_STATEMENTS.items()):
            if i:
                throttle.default_throttle.wait()
            fn = getattr(ak, fn_name, None)
            if fn is None:
                continue
            out[stmt] = fn(symbol=sym)
        return out

    def normalize_symbol(self, code: str, raw: Any, max_periods: int = 12, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for stmt, df in (raw or {}).items():
            recs = records(df)
            # newest first is typical; bound the number of periods stored.
            for r in recs[: max_periods * 2]:
                period = to_period_str(get(r, "REPORT_DATE", "报告日", "REPORT_DATE_NAME"))
                if not period:
                    continue
                data = {str(k): _clean(v) for k, v in r.items()}
                rows.append(
                    {
                        "code": code,
                        "report_period": period,
                        "statement": stmt,
                        "source": "em",
                        "data_json": data,
                    }
                )
        # de-dup + bound per statement (newest first as returned by 东财)
        bounded: list[dict[str, Any]] = []
        per_stmt: dict[str, int] = {}
        for r in rows:
            k = r["statement"]
            if per_stmt.get(k, 0) >= max_periods:
                continue
            per_stmt[k] = per_stmt.get(k, 0) + 1
            bounded.append(r)
        return bounded

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        id_map = security_id_map(session, [r["code"] for r in rows])
        for r in rows:
            r["security_id"] = id_map.get(r["code"])
        codes = list({r["code"] for r in rows})
        scope = select(FinancialStatement).where(
            FinancialStatement.code.in_(codes), FinancialStatement.source == "em"
        )
        return bulk_upsert(
            session, FinancialStatement, rows,
            key_fields=["code", "report_period", "statement", "source"],
            scope=scope,
        )


adapter = FinancialsEmAdapter()
