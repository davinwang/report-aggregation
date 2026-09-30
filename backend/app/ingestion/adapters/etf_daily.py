"""etf_daily — 场内基金 (ETF/LOF) daily bars, plus the Security rows that name them.

Why a separate adapter rather than folding ETFs into ``price_history``: the universe is
discovered, not configured. ``price_history`` iterates a fixed A-share ``universe``
(沪深300 etc.), but the ETF roster changes weekly and only the *liquid* tail is worth
storing — the full ~1700-name list would multiply daily bars for codes nobody looks at.
So this adapter resolves its universe from the live 场内基金 spot snapshot and keeps the
Top-N by 成交额, which is exactly the filter the 技术指标 signal matrix applies to decide
what counts as 低流动.

Structure mirrors ``index_daily``: a bulk adapter that loops the symbol list inside
``fetch`` (the pipeline's per-symbol path resolves codes from the A-share universe, which
is the wrong list for ETFs), with per-symbol error isolation so one dead code never
aborts the batch.

Source is Sina (``fund_etf_hist_sina``): 东财's ``fund_etf_hist_em`` is the richer call
but it is also the endpoint that throttles/blocks first, and ETF 份额折算 is rare enough
that 不复权 bars are acceptable (stored with ``adjust="none"``).

Codes are stored bare 6-digit (e.g. ``510300``): SH ETFs are 51/56/58xxxx, SZ ETFs
15xxxx — none of which collide with the A-share 60/68/00/30/43/83/87/92 prefixes. The
market prefix only exists inside the fetch call.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_date, to_float
from app.models.market import DailyQuote
from app.models.security import Security

logger = get_logger(__name__)

#: How many ETFs keep a bar history. The daily_close slot can afford a few dozen Sina
#: calls and the signal matrix reads ~40 rows, so 60 leaves headroom for growth.
DEFAULT_TOP_N = 60

#: The spot snapshot's columns drift with AkShare versions; these are the candidates.
_CODE_COLS = ("代码", "基金代码", "symbol", "code")
_NAME_COLS = ("名称", "基金名称", "简称")
_AMOUNT_COLS = ("成交额",)

_EXCHANGE = {"sh": "SSE", "sz": "SZSE", "bj": "BSE"}

#: Money-market / 现金管理 products. A raw Top-N by 成交额 is ~60% 银华日利/华宝添益/短融,
#: whose prices barely move — every technical signal on them reads 中性, which makes the
#: signal matrix a wall of nothing. Dropped by name so 债券ETF (a legitimate technical
#: subject) still gets in. ETF 简称 for this family is stable upstream.
_MONEY_MARKET_PATTERNS = ("货币", "日利", "添益", "现金", "理财", "收益")

#: Always-kept ETFs, merged ahead of the turnover ranking.
#:
#: A pure Top-N by 成交额 is the wrong universe for a *technical* page: the leaders
#: rotate with whatever theme is hot this month, and by the numbers most of the ETFs
#: users actually look at fall out — 沪深300ETF ranks ~34, 创业板50ETF ~59, 证券ETF ~83,
#: 酒ETF ~183. So the broad-based and the major single-theme products are pinned, and
#: turnover fills the remaining slots. Codes are the most liquid share class per fund
#: (the runner-ups — 159919 vs 510300, 588080 vs 588000 — are the same portfolio and
#: would just be a duplicate series in the matrix).
CORE_ETFS: tuple[str, ...] = (
    # 宽基
    "510300",  # 沪深300ETF
    "510500",  # 中证500ETF
    "510050",  # 上证50ETF
    "512100",  # 中证1000ETF
    "159915",  # 创业板ETF
    "588000",  # 科创50ETF
    "159949",  # 创业板50ETF
    "563300",  # 中证2000ETF
    "159781",  # 科创创业ETF
    # 风格
    "510880",  # 红利ETF
    "512890",  # 红利低波ETF
    # 行业 / 主题
    "512880",  # 证券ETF
    "512000",  # 券商ETF
    "512800",  # 银行ETF
    "512170",  # 医疗ETF
    "159992",  # 创新药ETF
    "512690",  # 酒ETF
    "159928",  # 消费ETF
    "512400",  # 有色金属ETF
    "515220",  # 煤炭ETF
    "588200",  # 科创芯片ETF
    "515880",  # 通信ETF
    "515030",  # 新能源车ETF
    "516160",  # 新能源ETF
    "515790",  # 光伏ETF
    "513050",  # 中概互联网ETF
    "513520",  # 日经ETF
    # 跨境 / 商品
    "513100",  # 纳指ETF
    "518880",  # 黄金ETF
    "159980",  # 有色ETF(商品)
    # 债券
    "511380",  # 可转债ETF
)


def _is_money_market(name: str) -> bool:
    return any(p in (name or "") for p in _MONEY_MARKET_PATTERNS)


def _split_symbol(symbol: str) -> tuple[str, str]:
    """``sh510300`` → (``510300``, ``SSE``). Unknown prefixes fall back to the raw code."""
    s = (symbol or "").strip().lower()
    for pfx, ex in _EXCHANGE.items():
        if s.startswith(pfx):
            return s[len(pfx):], ex
    return s, ""


def _etf_rows(df, include_money_market: bool = False) -> list[dict]:
    """Parse the 场内基金 spot frame into ``{code, name, symbol, exchange, amount}``.

    Ordered by ``CORE_ETFS`` first (in that order), then the rest by turnover and
    de-duplicated by code — so the refreshed set is both the products users expect to
    find and the ones actually trading, and an ETF demoted out of the tail simply stops
    being refreshed. Money-market products are excluded by default (see
    ``_MONEY_MARKET_PATTERNS``); ``include_money_market`` keeps them for the name-only
    master table, which wants the whole roster.
    """
    out: list[dict] = []
    for r in records(df):
        code, exchange = _split_symbol(clean_text(get(r, *_CODE_COLS), ""))
        if not code.isdigit() or len(code) != 6:
            continue
        name = clean_text(get(r, *_NAME_COLS), "") or code
        out.append({"code": code, "name": name,
                    "symbol": f"{_prefix_for(code, exchange)}{code}",
                    "exchange": exchange,
                    "amount": to_float(get(r, *_AMOUNT_COLS), 0.0) or 0.0,
                    "money_market": _is_money_market(name)})
    ranked = sorted(out, key=lambda x: -x["amount"])
    deduped: dict[str, dict] = {}
    for item in ranked:
        deduped.setdefault(item["code"], item)
    by_code = list(deduped.values())
    if include_money_market:
        return by_code
    core = [deduped[c] for c in CORE_ETFS
            if c in deduped and not deduped[c]["money_market"]]
    core_codes = {i["code"] for i in core}
    tail = [i for i in by_code if i["code"] not in core_codes and not i["money_market"]]
    return core + tail


def _prefix_for(code: str, exchange: str) -> str:
    for pfx, ex in _EXCHANGE.items():
        if ex == exchange:
            return pfx
    return "sh" if code.startswith(("5", "6")) else "sz"


def etf_universe(top_n: int = DEFAULT_TOP_N) -> list[dict]:
    """Top-``top_n`` 场内基金 by 成交额 (single upstream call, cached per run)."""
    return _etf_rows(get_ak().fund_etf_category_sina(symbol="ETF基金"))[: max(1, int(top_n))]


class EtfDailyAdapter(BaseAdapter):
    name = "etf_daily"
    description = "场内基金(ETF/LOF)日线行情 — 按成交额取流动性前 N 只, 新浪源 (不复权)"

    #: Resolved by :meth:`fetch`, consumed by :meth:`persist` to name the Securities.
    #: The pipeline passes ``codes``/``universe`` kwargs meant for per-symbol feeds and
    #: nothing for the discovered list, and ingestion runs one feed at a time behind the
    #: global ingest lock, so instance state is the simplest correct carrier.
    _universe: list[dict] = []

    def fetch(self, top_n: int = DEFAULT_TOP_N, **kwargs) -> Any:
        ak = get_ak()
        self._universe = _etf_rows(ak.fund_etf_category_sina(symbol="ETF基金"))[: max(1, int(top_n))]
        out: list[tuple[dict, Any]] = []
        for item in self._universe:
            throttle.default_throttle.wait()
            try:
                out.append((item, ak.fund_etf_hist_sina(symbol=item["symbol"])))
            except Exception as exc:  # noqa: BLE001 - one dead code must not kill the batch
                logger.warning("[etf_daily] %s failed: %s", item["code"], exc)
        return out

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
                    "amount": to_float(get(r, "amount", "成交额")),
                    "adjust": "none",
                    "source": "sina",
                })
        return rows

    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        return persist_bars(session, rows, meta=self._universe, sec_type="etf")


def persist_bars(session: Session, rows: list[dict[str, Any]], meta: list[dict] | None = None,
                 sec_type: str = "etf") -> int:
    """Upsert bars and make sure every code has a named ``Security`` row.

    Securities come from ``meta`` (the spot snapshot) when it has them and get a
    placeholder name otherwise, so the technical page's code search still resolves a
    bare ETF/transbond code typed by hand.
    """
    codes = sorted({r["code"] for r in rows})
    if not codes:
        return 0
    named = {item["code"]: item for item in meta or []}
    for code in codes:
        item = named.get(code) or {}
        ensure_security(session, code, item.get("name"), item.get("exchange"), sec_type)
    session.flush()
    id_map = {s.code: s.id for s in session.scalars(
        select(Security).where(Security.code.in_(codes))).all()}
    for r in rows:
        r["security_id"] = id_map.get(r["code"])
    scope = select(DailyQuote).where(DailyQuote.code.in_(codes), DailyQuote.adjust == "none")
    return bulk_upsert(session, DailyQuote, rows, key_fields=["code", "trade_date", "adjust"],
                       scope=scope)


def ensure_security(session: Session, code: str, name: str | None, exchange: str | None,
                    sec_type: str) -> None:
    """Insert a Security when absent. Never retypes an existing row.

    A bare code can legitimately already exist as a stock; the ETF/bond adapters only
    *add* master data, they don't reclassify the whole table. Callers pass each code
    once per run — a pending ``session.add`` isn't visible to a ``SELECT`` until flush,
    so checking and adding twice for one code would violate the code unique constraint.
    """
    if session.scalar(select(Security.id).where(Security.code == code)) is None:
        session.add(Security(code=code, name=name or code, type=sec_type,
                             exchange=exchange or "", is_active=True))


class EtfUniverseAdapter(BaseAdapter):
    """Registers every 场内基金 as a ``Security`` (names only, no bars).

    Bar history is expensive and only the liquid tail is worth it, but the *name* table
    should cover the whole market so the technical page's code search resolves ``512690``
    to ``半导体ETF``. Runs in ``weekly_master``.
    """

    name = "etf_universe"
    description = "场内基金(ETF/LOF)证券主档 — 全市场代码与简称 (不含行情)"

    def fetch(self, **kwargs) -> Any:
        df = get_ak().fund_etf_category_sina(symbol="ETF基金")
        return [{"code": i["code"], "name": i["name"], "exchange": i["exchange"], "type": "etf"}
                for i in _etf_rows(df, include_money_market=True)]

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
                session.add(Security(code=r["code"], name=r["name"], type="etf",
                                     exchange=r["exchange"], is_active=True))
                written += 1
            elif sec.name != r["name"]:
                # 简称 gets rewritten after 份额折算 — keep it fresh. Never retype an
                # existing row: a code can legitimately already exist as a stock.
                sec.name = r["name"]
                written += 1
        return written


adapter = EtfDailyAdapter()
universe_adapter = EtfUniverseAdapter()
