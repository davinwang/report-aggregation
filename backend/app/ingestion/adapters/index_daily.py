"""index_daily — key index daily bars via ``stock_zh_index_daily`` (Sina).

Index codes are stored with a market prefix (e.g. ``sh000300``) to avoid the classic
collision where 上证指数 ``000001`` would clash with 平安银行 ``000001``. These index
Securities (type=index) also serve as the spot leg for stock-index-futures basis.

``INDICES`` is grouped by role so the 技术指标 signal matrix can offer a 宽基-only view:
宽基 → 风格/主题 → 行业 → 债券。Codes are verified against Sina's ``stock_zh_index_daily``
(several legacy CSI codes — 000988/000990/000994/000985 — stop updating there and are
deliberately excluded rather than showing a stale last bar from years ago).
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

#: sina symbol -> (display name, exchange)
INDICES: dict[str, tuple[str, str]] = {
    # ---- 宽基 (broad-based) ----
    "sh000001": ("上证指数", "SSE"),
    "sz399001": ("深证成指", "SZSE"),
    "sh000300": ("沪深300", "SSE"),
    "sh000905": ("中证500", "SSE"),
    "sh000852": ("中证1000", "SSE"),
    "sh000016": ("上证50", "SSE"),
    "sz399006": ("创业板指", "SZSE"),
    "sh000688": ("科创50", "SSE"),
    # ---- 宽基补充 (size / breadth) ----
    "sh000010": ("上证180", "SSE"),
    "sh000903": ("中证100", "SSE"),
    "sh000906": ("中证800", "SSE"),
    "sz399005": ("中小100", "SZSE"),
    "sz399330": ("深证100", "SZSE"),
    "sz399673": ("创业板50", "SZSE"),
    "sz399303": ("国证2000", "SZSE"),
    "sz399102": ("创业板综", "SZSE"),
    # ---- 风格 / 主题 ----
    "sh000015": ("上证红利", "SSE"),
    "sh000698": ("科创100", "SSE"),
    "sh000932": ("中证消费", "SSE"),
    "sh000827": ("中证环保", "SSE"),
    # ---- 中证全指一级行业 ----
    "sh000986": ("全指能源", "SSE"),
    "sh000987": ("全指材料", "SSE"),
    "sh000989": ("全指可选", "SSE"),
    "sh000991": ("全指医药", "SSE"),
    "sh000992": ("全指金融", "SSE"),
    "sh000993": ("全指信息", "SSE"),
    # ---- 债券 ----
    "sh000012": ("上证国债指数", "SSE"),
}

#: Broad-based only — the default universe for the 技术指标 signal matrix when the user
#: hasn't picked one. 行业指数 overlap heavily with each other, so mixing them into a
#: single "全市场" vote would double-count the same risk exposure.
BROAD_INDICES: tuple[str, ...] = (
    "sh000001", "sz399001", "sh000300", "sh000905", "sh000852", "sh000016",
    "sz399006", "sh000688", "sh000010", "sh000903", "sh000906", "sz399005",
    "sz399330", "sz399673", "sz399303", "sz399102", "sh000698",
)


class IndexDailyAdapter(BaseAdapter):
    name = "index_daily"
    description = (
        f"主要指数日线行情 ({len(INDICES)} 条: 宽基/风格/中证全指一级行业/债券, 新浪源)"
    )

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
