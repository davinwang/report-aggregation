"""margin — 融资融券 (``stock_margin_sse`` range + ``stock_margin_szse`` daily summary).

Unit pitfall: the SSE frame reports 元 while the SZSE frame reports 亿元 — both are
normalized to 元 here so the two exchanges are directly comparable.

SZSE exposes a single date per call (no range), so the adapter walks back from the end
date over weekdays until a session returns data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import to_date, to_float
from app.models.flow import MarginData

logger = get_logger(__name__)

DEFAULT_DAYS = 20
SZSE_YI = 1e8  # SZSE frames are in 亿元


def _parse_ymd(s: Any) -> Optional[date]:
    if not s:
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    txt = str(s).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            continue
    return to_date(txt)


class MarginAdapter(BaseAdapter):
    name = "margin"
    description = "融资融券余额与买入额 (上交所区间 + 深交所快照)"

    def fetch(self, start: Any = None, end: Any = None, days: int = DEFAULT_DAYS, **kwargs) -> Any:
        ak = get_ak()
        end_d = _parse_ymd(end) or date.today()
        start_d = _parse_ymd(start) or (end_d - timedelta(days=max(7, days * 2)))

        out: dict[str, Any] = {"sse": None, "szse": None, "szse_date": None}

        throttle.default_throttle.wait()
        try:
            out["sse"] = ak.stock_margin_sse(
                start_date=start_d.strftime("%Y%m%d"), end_date=end_d.strftime("%Y%m%d")
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[margin] sse failed: %s", exc)

        # SZSE takes one date; walk back over weekdays until a session returns data.
        tried = 0
        for back in range(0, 10):
            d = end_d - timedelta(days=back)
            if d.weekday() >= 5:
                continue
            if tried >= 5:
                break
            tried += 1
            throttle.default_throttle.wait()
            try:
                df = ak.stock_margin_szse(date=d.strftime("%Y%m%d"))
            except Exception as exc:  # noqa: BLE001
                logger.debug("[margin] szse %s failed: %s", d, exc)
                continue
            if df is not None and not getattr(df, "empty", True):
                out["szse"] = df
                out["szse_date"] = d
                break
        return out

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        raw = raw or {}

        for r in records(raw.get("sse")):
            trade_date = to_date(get(r, "信用交易日期", "日期"))
            if trade_date is None:
                continue
            rows.append({
                "exchange": "SSE",
                "code": None,
                "trade_date": trade_date,
                "rzye": to_float(get(r, "融资余额")),
                "rzmre": to_float(get(r, "融资买入额")),
                "rqye": to_float(get(r, "融券余量金额", "融券余额")),
                "rzrqye": to_float(get(r, "融资融券余额")),
            })

        szse_date = raw.get("szse_date")
        for r in records(raw.get("szse")):
            if szse_date is None:
                continue
            rows.append({
                "exchange": "SZSE",
                "code": None,
                "trade_date": szse_date,
                "rzye": _scaled(get(r, "融资余额")),
                "rzmre": _scaled(get(r, "融资买入额")),
                "rqye": _scaled(get(r, "融券余额")),
                "rzrqye": _scaled(get(r, "融资融券余额")),
            })
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        exchanges = list({r["exchange"] for r in rows})
        dates = list({r["trade_date"] for r in rows})
        scope = select(MarginData).where(
            MarginData.exchange.in_(exchanges), MarginData.trade_date.in_(dates)
        )
        return bulk_upsert(
            session, MarginData, rows,
            key_fields=["exchange", "code", "trade_date"], scope=scope,
            mutable_fields=["rzye", "rzmre", "rqye", "rzrqye"],
        )


def _scaled(v: Any) -> Optional[float]:
    """SZSE values arrive in 亿元; scale to 元 for cross-exchange comparability."""
    f = to_float(v)
    return round(f * SZSE_YI, 2) if f is not None else None


adapter = MarginAdapter()
