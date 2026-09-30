"""技术信号矩阵 — 品种 × 指标 的方向表决 (the 参考页 signal-matrix model, for A股).

A single ``close`` price can't be called 偏多 or 偏空 on its own, so this module turns the
indicator engine into a **voting table**: each rule reads one indicator family and
returns one of

    bull  偏多   — the rule has an opinion, and it is up
    bear  偏空   — the rule has an opinion, and it is down
    neutral 中性 — the rule read the data and it says neither side
    abstain 弃权 — the rule *declines*: 超买/超卖, 无趋势, 样本不足, 指标不适用
    na     无数据 — there are no bars at all

弃权 and 无数据 are deliberately distinct from 中性, and both are kept **out of the
denominator**. That distinction is the whole point: a 超买 reading and a 震荡 reading
must not both add a "no vote" to the tally while meaning opposite things, and a missing
column must not be silently read as 中性.

Each row also carries ``net`` (Σ vote scores), ``bulls``/``bears`` (how many columns voted
each way) and ``voted`` (how many columns actually voted). A high ``net`` from three
columns is not the same evidence as from twelve, so both are returned.

Excluded from voting (but still listed, with a reason):
- **低流动** — latest 成交额 below the threshold, or a proxy when the feed has no 成交额.
  Thin books make every oscillator print noise.
- **滞后/停牌** — the last bar is several sessions behind the market's latest date.

Cached under ``quant.signal:{scope}:{cols}:{freq}:{limit}`` with the same TTL as the
existing matrix endpoint, and cleared whenever ingestion lands.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import cache_get, cache_set
from app.models.market import DailyQuote
from app.models.security import Security
from app.services.indicators import compute, resample_bars
from app.services.quotes import load_bars_bulk

# ---- states -------------------------------------------------------------------

BULL = "bull"
BEAR = "bear"
NEUTRAL = "neutral"
ABSTAIN = "abstain"
NA = "na"

STATE_LABELS: dict[str, str] = {
    BULL: "偏多", BEAR: "偏空", NEUTRAL: "中性", ABSTAIN: "弃权", NA: "无数据",
}

#: Scopes offered by the UI. ``index`` deliberately defaults to the broad-based list:
#: 行业指数 overlap heavily, so a single "全市场" vote over all of them would
#: double-count the same exposure.
SCOPES: tuple[str, ...] = ("index", "index+all", "etf", "bond", "stock", "all")

#: Bars loaded per symbol. Enough for a 60-bar DMI/ADX, a 250-bar volatility percentile
#: and a 5-year view's worth of warmup without a second query.
DEFAULT_BARS = 260

#: A symbol whose last bar is this many sessions behind the market's latest date is
#: treated as 停牌/滞后 and does not vote.
STALE_SESSIONS = 5

#: Minimum bars before percentile-based rules (波动分位) will speak at all.
PERCENTILE_MIN_BARS = 120

#: Default daily turnover floor (元) for participation in the vote. 5e7 ≈ 5000 万.
#: Overridable per call; ETFs and 可转债 have far thinner books than 沪深300 constituents
#: so the UI relaxes it for those scopes.
LIQUIDITY_FLOOR = 5e7


@dataclass(frozen=True)
class Rule:
    """One matrix column: a named indicator family plus its direction rule."""

    key: str
    label: str
    #: Indicator keys this rule needs. If ``compute`` produced none of them the column
    #: renders 无数据 rather than guessing.
    needs: tuple[str, ...]
    #: Rule body: (indicator frames, last close) -> (state, score, note).
    #: ``score`` is the vote weight (0 for neutral/abstain) and ``note`` is the one-line
    #: 口径 explanation shown on hover.
    fn: Callable[[dict[str, pd.DataFrame], float], tuple[str, float, str]]


@dataclass
class MatrixResult:
    rows: list[dict]
    columns: list[dict]
    summary: dict
    freq: str = "daily"
    as_of: Optional[str] = None
    meta: dict = field(default_factory=dict)


def _last(frame: Optional[pd.DataFrame], col: str) -> Optional[float]:
    if frame is None or col not in frame.columns or frame.empty:
        return None
    try:
        f = float(frame[col].iloc[-1])
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError, IndexError):
        return None


def _prev(frame: Optional[pd.DataFrame], col: str) -> Optional[float]:
    if frame is None or col not in frame.columns or len(frame) < 2:
        return None
    try:
        f = float(frame[col].iloc[-2])
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError, IndexError):
        return None


def _v(*vals: Optional[float]) -> bool:
    """True only when every argument is a usable number."""
    return all(v is not None and not (isinstance(v, float) and math.isnan(v)) for v in vals)


# ------------------------------ rules ------------------------------

def _r_ma_trend(ind, close):
    """均线趋势: 价格相对 MA20/MA60 的位置, 三档打分。"""
    ma = ind.get("ma")
    if not _v(close, _last(ma, "ma20"), _last(ma, "ma60")):
        return NA, 0.0, "均线未算出"
    c, m20, m60 = close, _last(ma, "ma20"), _last(ma, "ma60")
    if c >= m20 >= m60:
        return BULL, 2.0, "价 ≥ MA20 ≥ MA60 多头排列"
    if c <= m20 <= m60:
        return BEAR, 2.0, "价 ≤ MA20 ≤ MA60 空头排列"
    if c >= m20:
        return BULL, 1.0, "价在 MA20 上方但 MA60 未跟上"
    return BEAR, 1.0, "价在 MA20 下方"


def _r_ma_align(ind, close):
    """均线排列: 多头排列的均线对占比。"""
    al = ind.get("ma_align")
    v = _last(al, "ma_align")
    if v is None:
        ma = ind.get("ma")
        if not _v(_last(ma, "ma20"), _last(ma, "ma60")):
            return NA, 0.0, "样本不足"
        v = 100.0 if _last(ma, "ma5") >= _last(ma, "ma20") >= _last(ma, "ma60") else 0.0
    if v >= 75:
        return BULL, 2.0, f"多头排列占比 {v:.0f}%"
    if v <= 25:
        return BEAR, 2.0, f"空头排列占比 {100 - v:.0f}%"
    return NEUTRAL, 0.0, f"均线交织，占比 {v:.0f}%"


def _r_macd(ind, close):
    """MACD: DIF/DEA 相对位置 + 零轴。"""
    m = ind.get("macd")
    dif, dea = _last(m, "macd_dif"), _last(m, "macd_dea")
    if not _v(dif, dea):
        return NA, 0.0, "MACD 未算出"
    if dif > 0 and dif > dea:
        return BULL, 2.0, "DIF 在零轴上且在 DEA 之上"
    if dif < 0 and dif < dea:
        return BEAR, 2.0, "DIF 在零轴下且在 DEA 之下"
    if dif > dea:
        return BULL, 1.0, "金叉但在零轴下方，反弹性质"
    return BEAR, 1.0, "死叉但在零轴上方，弱反弹结束"


def _r_macd_cross(ind, close):
    """MACD 金叉/死叉: 只看最近一根, 是事件而不是状态。"""
    m = ind.get("macd")
    dif, dea, pdif, pdea = (_last(m, "macd_dif"), _last(m, "macd_dea"),
                            _prev(m, "macd_dif"), _prev(m, "macd_dea"))
    if not _v(dif, dea, pdif, pdea):
        return NA, 0.0, "MACD 未算出"
    golden = dif > dea and pdif <= pdea
    dead = dif < dea and pdif >= pdea
    if golden:
        return BULL, 2.0, "今日金叉"
    if dead:
        return BEAR, 2.0, "今日死叉"
    gap = dif - dea
    return NEUTRAL, 0.0, f"无交叉，柱体{'红' if gap >= 0 else '绿'}"


def _r_kdj(ind, close):
    """KDJ: 低位金叉/高位死叉给方向, 高位钝化与低位钝化都弃权。"""
    k = ind.get("kdj")
    kk, dd, kp, dp = _last(k, "kdj_k"), _last(k, "kdj_d"), _prev(k, "kdj_k"), _prev(k, "kdj_d")
    if not _v(kk, dd):
        return NA, 0.0, "KDJ 未算出"
    if kk >= 80:
        return ABSTAIN, 0.0, f"K={kk:.0f} 已进入超买区，此时不追多"
    if kk <= 20:
        return ABSTAIN, 0.0, f"K={kk:.0f} 已进入超卖区，此时不追空"
    if _v(kp, dp) and kk > dd and kp <= dp:
        return BULL, 2.0, "低位金叉"
    if _v(kp, dp) and kk < dd and kp >= dp:
        return BEAR, 2.0, "高位死叉"
    if kk > dd:
        return BULL, 1.0, "K 在 D 上方"
    return BEAR, 1.0, "K 在 D 下方"


def _r_rsi(ind, close):
    """RSI: 中位偏多/偏空, 极值区弃权（超买还能更超买）。"""
    r = ind.get("rsi")
    v = _last(r, "rsi12")
    if v is None:
        return NA, 0.0, "RSI 未算出"
    if v >= 80:
        return ABSTAIN, 0.0, f"RSI={v:.0f} 超买，不追多"
    if v <= 20:
        return ABSTAIN, 0.0, f"RSI={v:.0f} 超卖，不追空"
    if v >= 55:
        return BULL, 1.0, f"RSI={v:.0f} 中性偏强"
    if v <= 45:
        return BEAR, 1.0, f"RSI={v:.0f} 中性偏弱"
    return NEUTRAL, 0.0, f"RSI={v:.0f} 中性"


def _r_dmi(ind, close):
    """DMI: +DI/−DI 方向 + ADX 趋势强度。ADX 太低说明无趋势, 此时方向不可信。"""
    d = ind.get("dmi")
    pdi, mdi, adx = _last(d, "dmi_pdi"), _last(d, "dmi_mdi"), _last(d, "dmi_adx")
    if not _v(pdi, mdi, adx):
        return NA, 0.0, "DMI 未算出"
    if adx < 20:
        return ABSTAIN, 0.0, f"ADX={adx:.0f} 无明显趋势，此时方向不可信"
    if pdi > mdi:
        return BULL, 2.0, f"+DI 上穿 −DI（ADX={adx:.0f}）"
    return BEAR, 2.0, f"−DI 主导（ADX={adx:.0f}）"


def _r_boll(ind, close):
    """布林带: 触轨/突破给方向, 带内震荡中性。"""
    b = ind.get("boll")
    up, mid, low = _last(b, "boll_up"), _last(b, "boll_mid"), _last(b, "boll_low")
    if not _v(close, up, mid, low):
        return NA, 0.0, "布林带未算出"
    if close > up:
        return BULL, 2.0, "站上上轨，突破"
    if close < low:
        return BEAR, 2.0, "跌破下轨，破位"
    if close >= mid:
        return BULL, 1.0, "带内运行于中轴上方"
    return BEAR, 1.0, "带内运行于中轴下方"


def _r_boll_bw(ind, close):
    """带宽: 收敛时无方向可判（弃权）, 扩张且带外才确认。"""
    be = ind.get("boll_ext")
    bw = _last(be, "boll_bw")
    if bw is None:
        return NA, 0.0, "带宽未算出"
    frames = be.tail(120) if len(be) >= 40 else be
    hist = frames["boll_bw"].dropna()
    if len(hist) < 40:
        return ABSTAIN, 0.0, "样本不足，无法判断带宽收敛"
    pct = float((hist <= bw).mean() * 100)
    if pct <= 25:
        return ABSTAIN, 0.0, f"带宽处于近 120 日 {pct:.0f}% 分位，变盘前缩量收敛，方向待定"
    b = ind.get("boll")
    cu, cl = _last(b, "boll_up"), _last(b, "boll_low")
    if not _v(close, cu, cl):
        return NEUTRAL, 0.0, "带宽正常"
    if close > cu:
        return BULL, 1.0, f"带宽扩张（{pct:.0f}% 分位）且站上上轨"
    if close < cl:
        return BEAR, 1.0, f"带宽扩张（{pct:.0f}% 分位）且跌破下轨"
    return NEUTRAL, 0.0, f"带宽扩张（{pct:.0f}% 分位）但未出带"


def _r_brar(ind, close):
    """BRAR: 多空力量累计比。"""
    b = ind.get("brar")
    br, ar = _last(b, "brar_br"), _last(b, "brar_ar")
    if not _v(br, ar):
        return NA, 0.0, "BRAR 未算出"
    if br >= 100 and ar >= 100:
        return BULL, 2.0, f"BR={br:.0f} AR={ar:.0f} 双多"
    if br <= 100 and ar <= 100:
        return BEAR, 2.0, f"BR={br:.0f} AR={ar:.0f} 双空"
    if br >= 100:
        return BULL, 1.0, f"BR={br:.0f} 多方累计占优，AR 未同步"
    return BEAR, 1.0, f"BR={br:.0f} 空方累计占优，AR 未同步"


def _r_mfi(ind, close):
    """MFI: 带资金流的动量, 极值区弃权。"""
    m = ind.get("mfi")
    v = _last(m, "mfi")
    if v is None:
        return NA, 0.0, "MFI 未算出"
    if v >= 85:
        return ABSTAIN, 0.0, f"MFI={v:.0f} 资金极度超买"
    if v <= 15:
        return ABSTAIN, 0.0, f"MFI={v:.0f} 资金极度超卖"
    if v >= 60:
        return BULL, 1.0, f"MFI={v:.0f} 资金偏流入"
    if v <= 40:
        return BEAR, 1.0, f"MFI={v:.0f} 资金偏流出"
    return NEUTRAL, 0.0, f"MFI={v:.0f} 资金均衡"


def _r_obv(ind, close):
    """OBV: 量能是否确认价格方向。"""
    o = ind.get("obv")
    if o is None or len(o) < 20:
        return ABSTAIN, 0.0, "样本不足"
    s = o["obv"]
    now, ma = float(s.iloc[-1]), float(s.tail(10).mean())
    if not (math.isfinite(now) and math.isfinite(ma)):
        return NA, 0.0, "OBV 未算出"
    if now == ma:
        return NEUTRAL, 0.0, "量能与价格背离"
    return (BULL, 1.0, "量能高于均量，配合上涨") if now > ma else (
        BEAR, 1.0, "量能低于均量，承接不足")


def _r_bias(ind, close):
    """乖离率: 偏离均线过远时方向不可信（均值回归与追高都不成立）。"""
    b = ind.get("bias")
    v = _last(b, "bias20")
    if v is None:
        b6 = _last(b, "bias6")
        if b6 is None:
            return NA, 0.0, "乖离率未算出"
        v = b6
    if v >= 15:
        return ABSTAIN, 0.0, f"BIAS={v:.1f}% 正乖离过大，追高风险"
    if v <= -15:
        return ABSTAIN, 0.0, f"BIAS={v:.1f}% 负乖离过大，继续下跌风险"
    if v >= 3:
        return BULL, 1.0, f"BIAS={v:.1f}% 温和正偏离"
    if v <= -3:
        return BEAR, 1.0, f"BIAS={v:.1f}% 温和负偏离"
    return NEUTRAL, 0.0, f"BIAS={v:.1f}% 贴近均线"


def _r_hv(ind, close):
    """波动分位: 只描述风险，不给方向 —— 高波动时任何方向判断都更不可靠。"""
    h = ind.get("hv")
    if h is None:
        return NA, 0.0, "波动率未算出"
    s = h["hv"].dropna()
    if len(s) < PERCENTILE_MIN_BARS:
        return ABSTAIN, 0.0, "样本不足，算不出波动分位"
    now = float(s.iloc[-1])
    pct = float((s <= now).mean() * 100)
    if pct >= 80:
        return ABSTAIN, 0.0, f"波动率处于 {pct:.0f}% 分位，波动偏高——同样的仓位回撤会更大"
    if pct <= 20:
        return ABSTAIN, 0.0, f"波动率处于 {pct:.0f}% 分位，波动偏低"
    return NEUTRAL, 0.0, f"波动率处于 {pct:.0f}% 分位，正常"


def _r_roc(ind, close):
    """变动率: 中期动量方向。"""
    r = ind.get("roc")
    v = _last(r, "roc")
    if v is None:
        return NA, 0.0, "变动率未算出"
    if v >= 3:
        return BULL, 1.0, f"ROC={v:.1f}% 中期上行"
    if v <= -3:
        return BEAR, 1.0, f"ROC={v:.1f}% 中期下行"
    return NEUTRAL, 0.0, f"ROC={v:.1f}% 中期横盘"


def _r_sar(ind, close):
    """抛物线转向: 点在价上方/下方即多空。"""
    s = ind.get("sar")
    v = _last(s, "sar")
    if not _v(close, v):
        return NA, 0.0, "SAR 未算出"
    return (BULL, 1.0, "价在 SAR 点上方，多头持仓") if close > v else (
        BEAR, 1.0, "价在 SAR 点下方，空头持仓")


#: The default column set. Ordered 趋势 → 动量 → 震荡 → 量价 → 风险 so the table reads
#: left-to-right as "先看趋势，再看动能，然后是位置和量，最后是风险" — the order a
#: reader actually checks them in, and it keeps the correlated rules (MACD 与 金叉死叉)
#: adjacent instead of scattered.
DEFAULT_RULES: tuple[Rule, ...] = (
    Rule("ma_trend", "均线趋势", ("ma",), _r_ma_trend),
    Rule("ma_align", "均线排列", ("ma_align", "ma"), _r_ma_align),
    Rule("macd", "MACD", ("macd",), _r_macd),
    Rule("macd_cross", "金叉/死叉", ("macd",), _r_macd_cross),
    Rule("roc", "变动率", ("roc",), _r_roc),
    Rule("kdj", "KDJ", ("kdj",), _r_kdj),
    Rule("rsi", "RSI", ("rsi",), _r_rsi),
    Rule("dmi", "DMI 趋势", ("dmi",), _r_dmi),
    Rule("boll", "布林带", ("boll",), _r_boll),
    Rule("brar", "BRAR 情绪", ("brar",), _r_brar),
    Rule("mfi", "MFI 资金", ("mfi",), _r_mfi),
    Rule("obv", "OBV 量能", ("obv",), _r_obv),
    Rule("bias", "乖离率", ("bias",), _r_bias),
    Rule("hv", "波动分位", ("hv",), _r_hv),
)

RULES: dict[str, Rule] = {r.key: r for r in DEFAULT_RULES}

#: Indicators the default matrix needs — one ``compute`` pass per symbol covers every
#: column. Kept for introspection (and asserted against the rule set in the tests);
#: ``_vote`` deliberately does *not* read it, so a caller passing a custom rule subset
#: gets that subset's indicators computed instead of 无数据.
REQUIRED_INDICATORS: tuple[str, ...] = tuple(
    dict.fromkeys(k for rule in DEFAULT_RULES for k in rule.needs)
)


# ------------------------------ universe ------------------------------

def resolve_codes(session: Session, scope: str = "index", limit: int = 120) -> list[str]:
    """Codes for a scope, most-liquid first when the scope is large.

    Ordering matters as much as membership: ``index`` returns ~30 codes but ``stock``
    returns thousands, and the matrix is capped at ``limit``. Ordering by latest bar date
    (not by code) puts what actually traded on top.
    """
    scope = scope if scope in SCOPES else "index"
    types: list[str] = []
    if scope == "index":
        from app.ingestion.adapters.index_daily import BROAD_INDICES

        existing = set(session.scalars(
            select(Security.code).where(Security.type == "index")).all())
        return [c for c in BROAD_INDICES if c in existing][:limit]
    if scope == "index+all":
        types = ["index"]
    elif scope == "all":
        types = ["index", "etf", "bond", "stock"]
    else:
        types = [scope]
    rows = session.execute(
        select(Security.code)
        .join(DailyQuote, DailyQuote.security_id == Security.id)
        .where(Security.type.in_(types), Security.is_active.is_(True))
        .group_by(Security.code)
        .order_by(func.max(DailyQuote.trade_date).desc())
        .limit(max(1, limit))
    ).all()
    return [c for (c,) in rows]


# ------------------------------ matrix ------------------------------

def build(session: Session, scope: str = "index", columns: Optional[list[str]] = None,
          freq: str = "daily", limit: int = 120, bars: int = DEFAULT_BARS,
          liquidity_floor: float = LIQUIDITY_FLOOR) -> MatrixResult:
    """Compute the signal matrix (uncached — see :func:`snapshot` for the cached read)."""
    rules = _resolve_rules(columns)
    scope = scope if scope in SCOPES else SCOPES[0]
    codes = resolve_codes(session, scope=scope, limit=limit)
    key = freq if freq in ("daily", "weekly", "monthly") else "daily"
    frames = load_bars_bulk(session, codes, limit=bars)

    # The staleness reference is the latest session *within this universe*, not the
    # database's global max. "停牌" means a name stopped trading while its peers kept
    # going; using a global max would instead mean "whose ingestion job hasn't run
    # yet" — so refreshing the ETF feed would silently mark every stale-but-fine stock
    # as 停牌 and empty the 个股 tab. Deriving it from the frames already in hand is
    # both scoped and free.
    last_dates = {
        code: str(df["date"].iloc[-1])[:10]
        for code, df in frames.items()
        if df is not None and not df.empty and "date" in df.columns
    }
    ref = max(last_dates.values(), default=None)
    ref_date = date.fromisoformat(ref) if ref else None

    rows: list[dict] = []
    excluded = {"低流动": 0, "滞后/停牌": 0, "无行情": 0}
    for code in codes:
        df = frames.get(code)
        if df is None or df.empty:
            excluded["无行情"] += 1
            rows.append(_placeholder_row(session, code, code, NA, "暂无日线数据", 0))
            continue
        if key != "daily":
            df = resample_bars(df, key)
            if df is None or df.empty:
                excluded["无行情"] += 1
                rows.append(_placeholder_row(session, code, code, NA, "重采样后无数据", 0))
                continue
        sec = session.scalar(select(Security).where(Security.code == code))
        close = float(df["close"].iloc[-1])
        turnover = _turnover(df)
        votes, bull, bear, neutral, abstain = _vote(df, rules, close)
        stale = _is_stale(df, ref_date)
        thin = turnover is not None and turnover < liquidity_floor
        if stale or thin:
            # The readings stay visible (they're real) but the row doesn't count toward
            # the market tally — a 停牌 name's indicators describe a price that hasn't
            # traded in a week.
            excluded["滞后/停牌" if stale else "低流动"] += 1
        net = sum(v["score"] for v in votes.values() if v["voted"])
        voted = sum(1 for v in votes.values() if v["voted"])
        rows.append({
            "code": code,
            "name": (sec.name if sec else code) or code,
            "type": (sec.type if sec else ""),
            "exchange": (sec.exchange if sec else ""),
            "date": str(df["date"].iloc[-1]),
            "close": round(close, 4),
            "change_pct": _round(_change_pct(df)),
            "turnover": _round(turnover, 0),
            "signals": votes,
            "bulls": bull,
            "bears": bear,
            "neutrals": neutral,
            "abstains": abstain,
            "voted": voted,
            "net": round(net, 2),
            "verdict": _verdict(bull, bear),
            "excluded": ("低流动" if thin else "滞后/停牌" if stale else None),
        })

    payload = MatrixResult(
        rows=rows,
        columns=[{"key": r.key, "label": r.label, "states": STATE_LABELS} for r in rules],
        summary=_summarize(rows, rules, excluded),
        freq=key,
        as_of=ref,
        meta={"scope": scope, "limit": limit, "bars": bars,
              "liquidity_floor": liquidity_floor,
              "universe": len(codes),
              "excluded": excluded},
    )
    return payload


def snapshot(session: Session, scope: str = "index", columns: Optional[list[str]] = None,
             freq: str = "daily", limit: int = 120,
             liquidity_floor: float = LIQUIDITY_FLOOR) -> dict:
    """Cached :func:`build`, keyed on everything that changes the result.

    Cached like the existing matrix endpoint: DB change-counter + 30-min TTL.
    """
    cache_key = cache_key_for(scope=scope, columns=columns, freq=freq, limit=limit,
                              liquidity_floor=liquidity_floor)
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    res = build(session, scope=scope, columns=columns, freq=freq, limit=limit,
                liquidity_floor=liquidity_floor)
    payload = {"rows": res.rows, "columns": res.columns, "summary": res.summary,
               "freq": res.freq, "as_of": res.as_of, "meta": res.meta}
    cache_set(cache_key, payload)
    return payload


def cache_key_for(scope: str = "index", columns: Optional[list[str]] = None,
                  freq: str = "daily", limit: int = 120,
                  liquidity_floor: float = LIQUIDITY_FLOOR) -> str:
    """The cache key for one parameter set.

    Public because the prewarmer has to name the key it warms; it is the single place
    that decides what distinguishes one cached payload from another, so ``snapshot``
    and the prewarm list can't drift into warming keys nobody reads (or vice versa).
    """
    return (f"quant.signal:{scope}:{_column_key(columns)}:{freq}:{limit}"
            f":{int(liquidity_floor)}")


def _resolve_rules(columns: Optional[list[str]]) -> list[Rule]:
    if not columns:
        return list(DEFAULT_RULES)
    out: list[Rule] = []
    for key in columns:
        rule = RULES.get((key or "").strip().lower())
        if rule is not None:
            out.append(rule)
    return out or list(DEFAULT_RULES)


def _column_key(columns: Optional[list[str]]) -> str:
    """Cache-key fragment for the requested column set (resolved, so order/aliases
    that select the same rules share one entry)."""
    return ",".join(r.key for r in _resolve_rules(columns)) or "default"


def _vote(df: pd.DataFrame, rules: list[Rule], close: float) -> tuple[dict, int, int, int, int]:
    """Run every rule against one frame and tally the states.

    Computes the union of the requested rules' indicator needs rather than the fixed
    ``REQUIRED_INDICATORS`` set, so a caller passing a custom rule subset still gets
    data for it instead of a table of 无数据.
    """
    needs = [k for rule in rules for k in rule.needs]
    ind = compute(df, list(dict.fromkeys(needs)))
    votes: dict[str, dict] = {}
    bull = bear = neutral = abstain = 0
    for rule in rules:
        if not any(k in ind for k in rule.needs):
            state, score, note = NA, 0.0, "指标不适用于该品种"
        else:
            try:
                state, score, note = rule.fn(ind, close)
            except Exception:  # noqa: BLE001 - one broken rule must not lose the row
                state, score, note = NA, 0.0, "规则计算失败"
        # Rules return the **magnitude** of their opinion (0-2); the sign is applied here
        # so a rule author can't accidentally vote 偏空 with a positive weight. 弃权/无数据
        # never vote: the score is forced to 0 so a weight returned alongside an abstain
        # can't leak into the net tally either.
        voted = state in (BULL, BEAR)
        if not voted:
            score = 0.0
        signed = score if state == BULL else -score if state == BEAR else 0.0
        votes[rule.key] = {"state": state, "label": STATE_LABELS[state],
                           "score": round(signed, 2), "voted": voted, "note": note}
        bull += state == BULL
        bear += state == BEAR
        neutral += state == NEUTRAL
        abstain += state in (ABSTAIN, NA)
    return votes, bull, bear, neutral, abstain


def _turnover(df: pd.DataFrame) -> Optional[float]:
    """Latest 成交额, or a volume×close proxy for feeds without it.

    可转债 and index bars carry no 成交额, but a liquidity gate that silently returned
    "unknown" for them would read as "liquid" and let illiquid names into the vote.
    """
    if "amount" in df.columns:
        v = df["amount"].dropna()
        if len(v):
            return float(v.iloc[-1])
    if "volume" in df.columns and "close" in df.columns:
        v = (df["volume"] * df["close"]).dropna()
        if len(v):
            return float(v.iloc[-1])
    return None


def _is_stale(df: pd.DataFrame, ref: Optional[date]) -> bool:
    """Whether the last bar sits too far behind the market's latest session.

    Compared in calendar days with a 2× session allowance, because a run of  holidays
    makes 5 sessions span 9-10 calendar days and a naive 5-day cutoff would flag every
    instrument around 国庆/春节.
    """
    if ref is None:
        return False
    last = str(df["date"].iloc[-1])
    try:
        d = date.fromisoformat(last[:10])
    except ValueError:
        return False
    return (ref - d).days > STALE_SESSIONS * 2


def _change_pct(df: pd.DataFrame) -> Optional[float]:
    if len(df) < 2:
        return None
    prev, now = float(df["close"].iloc[-2]), float(df["close"].iloc[-1])
    return 100 * (now - prev) / prev if prev else None


def _verdict(bull: int, bear: int) -> str:
    if bull and bull > bear:
        return "偏多"
    if bear and bear > bull:
        return "偏空"
    if bull == bear and bull:
        return "分歧"
    return "无方向"


def _placeholder_row(session: Session, code: str, name: str, state: str,
                     note: str, voted: int) -> dict:
    sec = session.scalar(select(Security).where(Security.code == code))
    return {"code": code, "name": (sec.name if sec else name) or code,
            "type": (sec.type if sec else ""), "exchange": (sec.exchange if sec else ""),
            "date": None, "close": None, "change_pct": None, "turnover": None,
            "signals": {}, "bulls": 0, "bears": 0, "neutrals": 0, "abstains": 0,
            "voted": voted, "net": 0.0, "verdict": "无数据", "excluded": note}


def _summarize(rows: list[dict], rules: list[Rule], excluded: dict) -> dict:
    """Column tallies + the market net direction, counting only rows that voted.

    The per-column counts are computed over *participating* rows only: including
    低流动/停牌 names would drag every column toward 中性 for reasons that have nothing
    to do with the indicator, and would make the "净方向" disagree with the row list.
    """
    live = [r for r in rows if r.get("excluded") is None and r.get("signals")]
    cols = {}
    for rule in rules:
        counts = {BULL: 0, BEAR: 0, NEUTRAL: 0, ABSTAIN: 0, NA: 0}
        for r in live:
            v = r["signals"].get(rule.key)
            if v:
                counts[v["state"]] += 1
        decided = counts[BULL] + counts[BEAR]
        cols[rule.key] = {
            **counts,
            "bull_pct": round(100 * counts[BULL] / len(live), 1) if live else 0.0,
            "bear_pct": round(100 * counts[BEAR] / len(live), 1) if live else 0.0,
            "decided": decided,
            "abstain_pct": round(100 * counts[ABSTAIN] / len(live), 1) if live else 0.0,
            "net": counts[BULL] - counts[BEAR],
        }
    bulls = sum(r["bulls"] for r in live)
    bears = sum(r["bears"] for r in live)
    no_vote = sum(1 for r in live if r["voted"] == 0)
    # "分歧" over zero voters would read as a real disagreement rather than the absence
    # of one, so an empty ballot gets its own verdict.
    verdict = ("无表决" if not live else "偏多" if bulls > bears
               else "偏空" if bears > bulls else "分歧" if bulls or bears else "无表决")
    return {
        "total": len(rows),
        "participating": len(live),
        "excluded": excluded,
        "excluded_total": sum(excluded.values()),
        "columns": cols,
        "market_net": bulls - bears,
        "market_verdict": verdict,
        "breadth": {
            "bull": sum(1 for r in live if r["verdict"] == "偏多"),
            "bear": sum(1 for r in live if r["verdict"] == "偏空"),
            "split": sum(1 for r in live if r["verdict"] == "分歧"),
            "flat": sum(1 for r in live if r["verdict"] == "无方向"),
        },
        "no_vote": no_vote,
    }


def _round(v: Optional[float], digits: int = 4) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return None if not math.isfinite(f) else round(f, digits)
    except (TypeError, ValueError):
        return None


def rules_catalog() -> list[dict]:
    """Column definitions for the UI (key, label, rule text, needed indicators)."""
    return [{"key": r.key, "label": r.label, "needs": list(r.needs),
             "doc": (r.fn.__doc__ or "").strip()} for r in DEFAULT_RULES]
