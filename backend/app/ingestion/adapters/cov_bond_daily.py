"""cov_bond_daily — 可转债 (可转换公司债券) daily bars + the Security rows that name them.

可转债 belong on the 技术指标 page for the same reason ETFs do: they trade like equity
(涨跌幅限制为 20%/次日, T+0) but are anchored to a 转股价, so 均线/布林/MACD on a 转债
carries information the underlying stock's own chart does not — the premium the market
is paying for the conversion option. 东方财富's equity interfaces don't cover them, so
this is a separate adapter writing into the shared ``daily_quote`` table.

Source is ``bond_zh_hs_cov_daily`` (Sina), one call per bond. The universe comes from
``bond_zh_hs_cov_spot`` (all listed 转债 with today's price/volume/amount) and is cut to
the Top-N by 成交额 for the same reason as ETFs: ~330 names is too many daily Sina calls
for the close-of-day slot, and the illiquid tail has no readable technical signal anyway.

Exchange prefixes matter here and cannot be derived from the code range alone: 沪市转债
are 110/111/113/118xxxx, 深市转债 are 123/127/128xxxx, and both markets use 12xxxx, so
the prefix comes from the snapshot's own ``symbol`` field. Codes are stored bare 6-digit
(none of those prefixes collide with the A-share 60/68/00/30/43/83/87/92 ranges).

Bars are 不复权 (``adjust="none"``): 转债 share the equity market's unadjusted quote
convention, and 赎回/回售 jumps are real events here, not artifacts to smooth away.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.adapters.etf_daily import persist_bars
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_date, to_float
from app.models.security import Security

logger = get_logger(__name__)

#: How many 转债 keep a bar history — sized to the daily_close budget, not to the
#: ~330-name market.
DEFAULT_TOP_N = 50

_EXCHANGE = {"sh": "SSE", "sz": "SZSE", "bj": "BSE"}

#: ``bond_zh_hs_cov_spot`` column candidates (the frame gained ``code``/``ticktime``
#: over AkShare releases; ``symbol`` alone is not stable enough to rely on).
_SYMBOL_COLS = ("symbol", "代码", "转债代码")
_CODE_COLS = ("code", "转债代码", "代码")
_NAME_COLS = ("name", "转债名称", "名称")
_AMOUNT_COLS = ("amount", "成交额")


def _split_symbol(symbol: str) -> tuple[str, str]:
    s = (symbol or "").strip().lower()
    for pfx, ex in _EXCHANGE.items():
        if s.startswith(pfx):
            return s[len(pfx):], ex
    return s, ""


def _bond_rows(df) -> list[dict]:
    """Parse the 转债 spot frame into ``{code, name, symbol, exchange, amount}``.

    Sorted by turnover and de-duplicated by code so the refreshed set tracks liquidity.
    """
    out: list[dict] = []
    for r in records(df):
        raw = clean_text(get(r, *_SYMBOL_COLS), "")
        code, exchange = _split_symbol(raw)
        if not code.isdigit() or len(code) != 6:
            # Older frames have no ``symbol``; fall back to the bare code, which then
            # only tells us the code — the exchange is left blank rather than guessed.
            code = clean_text(get(r, *_CODE_COLS), "")
            exchange = ""
        if not code.isdigit() or len(code) != 6:
            continue
        out.append({"code": code, "name": clean_text(get(r, *_NAME_COLS), "") or code,
                    "symbol": f"{_prefix_for(code, exchange)}{code}",
                    "exchange": exchange,
                    "amount": to_float(get(r, *_AMOUNT_COLS), 0.0) or 0.0})
    deduped: dict[str, dict] = {}
    for item in sorted(out, key=lambda x: -x["amount"]):
        deduped.setdefault(item["code"], item)
    return list(deduped.values())


def _prefix_for(code: str, exchange: str) -> str:
    """Sina symbol prefix. Falls back to the code ranges when upstream gave no exchange."""
    for pfx, ex in _EXCHANGE.items():
        if exchange and ex == exchange:
            return pfx
    # No prefix upstream: 沪市转债 are 110/111/113, 深市 123/127/128. The fetch retries
    # the other market, so a wrong guess here costs one call rather than the bond.
    return "sh" if code.startswith(("110", "111", "113")) else "sz"


class CovBondDailyAdapter(BaseAdapter):
    name = "cov_bond_daily"
    description = "可转债日线行情 — 按成交额取流动性前 N 只, 新浪源 (不复权)"

    _universe: list[dict] = []

    def fetch(self, top_n: int = DEFAULT_TOP_N, **kwargs) -> Any:
        ak = get_ak()
        self._universe = _bond_rows(ak.bond_zh_hs_cov_spot())[: max(1, int(top_n))]
        out: list[tuple[dict, Any]] = []
        for item in self._universe:
            throttle.default_throttle.wait()
            frame = self._fetch_one(ak, item)
            if frame is not None:
                out.append((item, frame))
        return out

    @staticmethod
    def _fetch_one(ak, item: dict) -> Any:
        """Fetch one bond's bars, retrying the other market when the prefix was guessed."""
        primary = item["symbol"]
        alternate = ("sz" + item["code"] if primary.startswith("sh")
                     else "sh" + item["code"])
        for symbol in (primary, alternate):
            try:
                df = ak.bond_zh_hs_cov_daily(symbol=symbol)
                if df is not None and len(df) > 0:
                    item["exchange"] = {"sh": "SSE", "sz": "SZSE"}[symbol[:2]]
                    return df
            except Exception as exc:  # noqa: BLE001 - try the other exchange
                logger.debug("[cov_bond_daily] %s failed: %s", symbol, exc)
        logger.warning("[cov_bond_daily] %s no data on either exchange", item["code"])
        return None

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item, frame in raw or []:
            for r in records(frame):
                d = to_date(get(r, "date", "日期"))
                close = to_float(get(r, "close", "收盘"))
                if d is None or close is None:
                    continue
                rows.append({
                    "code": item["code"],
                    "trade_date": d,
                    "open": to_float(get(r, "open", "开盘")),
                    "high": to_float(get(r, "high", "最高")),
                    "low": to_float(get(r, "low", "最低")),
                    "close": close,
                    "volume": to_float(get(r, "volume", "成交量")),
                    "adjust": "none",
                    "source": "sina",
                })
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        return persist_bars(session, rows, meta=self._universe, sec_type="bond")


class CovBondUniverseAdapter(BaseAdapter):
    """Registers every listed 可转债 as a ``Security`` (names only, no bars).

    Same split as ETFs: the whole ~330-name master table is cheap and makes the code
    search complete, while bar history stays limited to the liquid tail. Runs in
    ``weekly_master``.
    """

    name = "cov_bond_universe"
    description = "可转债证券主档 — 全市场代码与简称 (不含行情)"

    def fetch(self, **kwargs) -> Any:
        rows = _bond_rows(get_ak().bond_zh_hs_cov_spot())
        return [{"code": r["code"], "name": r["name"], "exchange": r["exchange"], "type": "bond"}
                for r in rows]

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        return raw or []

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        if not rows:
            return 0
        existing = {s.code: s for s in session.scalars(
            select(Security).where(Security.code.in_([r["code"] for r in rows]))).all()}
        written = 0
        for r in rows:
            sec = existing.get(r["code"])
            if sec is None:
                session.add(Security(code=r["code"], name=r["name"], type="bond",
                                     exchange=r["exchange"], is_active=True))
                written += 1
            elif sec.name != r["name"]:
                sec.name = r["name"]
                written += 1
        return written


adapter = CovBondDailyAdapter()
universe_adapter = CovBondUniverseAdapter()
