"""index_daily — key index daily bars via ``stock_zh_index_daily`` (Sina).

Index codes are stored with a market prefix (e.g. ``sh000300``) to avoid the classic
collision where 上证指数 ``000001`` would clash with 平安银行 ``000001``. These index
Securities (type=index) also serve as the spot leg for stock-index-futures basis.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion import throttle
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import to_date, to_float
from app.core.logging import get_logger
from app.models.market import DailyQuote
from app.models.security import Security

logger = get_logger(__name__)

# sina symbol -> (display name, exchange)
INDICES: dict[str, tuple[str, str]] = {
    "sh000001": ("上证指数", "SSE"),
    "sz399001": ("深证成指", "SZSE"),
    "sh000300": ("沪深300", "SSE"),
    "sh000905": ("中证500", "SSE"),
    "sh000852": ("中证1000", "SSE"),
    "sh000016": ("上证50", "SSE"),
    "sz399006": ("创业板指", "SZSE"),
    "sh000688": ("科创50", "SSE"),
}


class IndexDailyAdapter(BaseAdapter):
    name = "index_daily"
    description = "主要指数日线行情 (上证/深证/沪深300/中证500/1000/上证50/创业板/科创50)"

    def fetch(self, symbols: list[str] | None = None, **kwargs) -> Any:
        ak = get_ak()
        out: list[tuple[str, Any]] = []
        for sym in symbols or list(INDICES.keys()):
            throttle.default_throttle.wait()
            try:
                out.append((sym, ak.stock_zh_index_daily(symbol=sym)))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[index_daily] %s failed: %s", sym, exc)
        return out

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for sym, df in raw or []:
            for r in records(df):
                d = to_date(get(r, "date", "日期"))
                close = to_float(get(r, "close", "收盘"))
                if d is None or close is None:
                    continue
                rows.append(
                    {
                        "code": sym,
                        "trade_date": d,
                        "open": to_float(get(r, "open", "开盘")),
                        "high": to_float(get(r, "high", "最高")),
                        "low": to_float(get(r, "low", "最低")),
                        "close": close,
                        "volume": to_float(get(r, "volume", "成交量")),
                        "adjust": "none",
                        "source": "sina",
                    }
                )
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        # Ensure index Securities exist.
        for sym, (nm, ex) in INDICES.items():
            sec = session.scalar(select(Security).where(Security.code == sym))
            if sec is None:
                session.add(Security(code=sym, name=nm, type="index", exchange=ex, is_active=True))
        session.flush()
        id_map = {s.code: s.id for s in session.scalars(select(Security).where(Security.type == "index")).all()}
        for r in rows:
            r["security_id"] = id_map.get(r["code"])
        codes = list({r["code"] for r in rows})
        scope = select(DailyQuote).where(DailyQuote.code.in_(codes))
        return bulk_upsert(session, DailyQuote, rows, key_fields=["code", "trade_date", "adjust"], scope=scope)


adapter = IndexDailyAdapter()
