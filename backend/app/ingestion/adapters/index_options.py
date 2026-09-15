"""index_options — 中金所股指期权 (IO/MO/HO) T型报价 via ``option_finance_board``.

The AkShare frame is a *live snapshot* of the current session with columns
``instrument`` / ``position`` (持仓量) / ``volume`` / ``lastprice`` / ``updown``, where the
strike and call/put flag are embedded in the instrument code (``IO2612-C-3900``).

Stored under the newest trade date already in the DB (``index_daily``) so weekend /
holiday runs still stamp the correct trading session. 涨跌 is preserved by
reconstructing ``pre_settle = lastprice − updown`` (the model has no updown column).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_float
from app.models.market import OptionQuote
from app.services import options as options_svc

logger = get_logger(__name__)

UNDERLYINGS = list(options_svc.UNDERLYINGS)
MONTH_LOOKAHEAD = 5


class IndexOptionsAdapter(BaseAdapter):
    name = "index_options"
    description = "沪深300/中证1000/上证50 股指期权 T型报价 (IO/MO/HO)"

    def fetch(self, ref: Optional[date] = None, **kwargs) -> Any:
        ak = get_ak()
        ref = ref if isinstance(ref, date) else date.today()
        out: list[tuple[str, Any]] = []
        for underlying in UNDERLYINGS:
            for month in options_svc.months_for_ref(ref, MONTH_LOOKAHEAD):
                throttle.default_throttle.wait()
                try:
                    df = ak.option_finance_board(symbol=underlying, end_month=month)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("[index_options] %s %s failed: %s", underlying, month, exc)
                    continue
                if df is not None and getattr(df, "empty", True) is False:
                    out.append((f"{underlying}|{month}", df))
        return out

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, df in raw or []:
            underlying, _, month = key.partition("|")
            for r in records(df):
                instrument = (clean_text(get(r, "instrument", "合约编码", "合约交易代码"), "") or "").upper()
                parsed = options_svc.parse_instrument(instrument)
                if parsed is None:
                    continue
                last = to_float(get(r, "lastprice", "最新价", "收盘价"))
                updown = to_float(get(r, "updown", "涨跌"))
                rows.append({
                    "underlying": underlying,
                    "end_month": month or parsed["end_month"],
                    "contract_code": instrument,
                    "strike": parsed["strike"],
                    "cp": parsed["cp"],
                    "close": last,
                    # 涨跌 = 最新价 − 昨结算价 → recover 昨结算价 for the model.
                    "pre_settle": (round(last - updown, 4) if (last is not None and updown is not None) else None),
                    "volume": to_float(get(r, "volume", "成交量")),
                    "oi": to_float(get(r, "position", "持仓量")),
                })
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        if not rows:
            return 0
        trade_date = options_svc.latest_trade_date(session) or date.today()
        for r in rows:
            r["trade_date"] = trade_date
        codes = list({r["contract_code"] for r in rows})
        scope = select(OptionQuote).where(OptionQuote.contract_code.in_(codes))
        return bulk_upsert(
            session, OptionQuote, rows,
            key_fields=["contract_code", "trade_date"], scope=scope,
            mutable_fields=[
                "underlying", "end_month", "strike", "cp", "close",
                "pre_settle", "volume", "oi",
            ],
        )


adapter = IndexOptionsAdapter()
