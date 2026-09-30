"""Technical indicator engine — pure numpy/pandas (NO TA-Lib / pandas-ta).

Rationale (per plan): TA-Lib has painful native builds on Windows and pandas-ta has
maintenance risk, so indicators are implemented directly. Formulas follow the common
通达信/同花顺 definitions so values match what CN users expect.

Input DataFrame columns (case-insensitive, at least): open, high, low, close, volume.
Optional: amount, turnover_rate, oi.

Every ``ind_*`` function takes its periods as keyword arguments, so the UI can retune
the common ones (MA/BOLL/MACD/RSI…) without new endpoints: ``compute(df, ["ma"],
{"ma": {"periods": [5, 10, 20]}})``. Unknown parameters raise ``TypeError``, which
``compute`` treats as "skip this indicator" rather than failing the whole request.

Public API:
    compute(df, names, params) -> dict[str, pd.DataFrame]
    build_series(df, names, bars, code, freq, params) -> ECharts-ready dict
    catalog() -> dict  (Chinese label / group / pane / formula per indicator)
    resample_bars(df, freq) -> pd.DataFrame  (daily -> weekly|monthly)
    INDICATORS / ALIASES / INDICATOR_META registries
"""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd

# ----------------------------- primitives -----------------------------

def _col(df: pd.DataFrame, *names: str) -> pd.Series:
    for n in names:
        if n in df.columns:
            return df[n].astype(float)
    raise KeyError(f"missing column, expected one of {names}")


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _sma_cn(s: pd.Series, n: int, m: int = 1) -> pd.Series:
    """通达信 SMA(X,N,M) == EWM with alpha=M/N."""
    return s.ewm(alpha=m / n, adjust=False).mean()


def _ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=1).mean()


def _hhv(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=1).max()


def _llv(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=1).min()


def _tr(df: pd.DataFrame) -> pd.Series:
    high, low, close = _col(df, "high"), _col(df, "low"), _col(df, "close")
    pc = close.shift(1)
    return pd.concat([(high - low), (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)


def _opt_col(df: pd.DataFrame, name: str) -> pd.Series | None:
    """Optional numeric column, or None when the feed doesn't carry it.

    Volume-only sources (Sina ETF/bond bars, index bars) have no 成交额/换手率, so the
    indicators that need them must degrade to None instead of raising — otherwise one
    missing column would silently drop half the indicator set.
    """
    if name not in df.columns:
        return None
    return df[name].astype(float)


def _seq(value, cast, default):
    """Coerce a period spec into a validated sequence.

    Accepts ``20`` → ``[20]``, ``(5, 10, 20)``, ``"5,10,20"`` and ``[5, 10, 20]`` so the
    same parameter can come from a query string or a JSON body. Anything unusable falls
    back to the indicator's own default rather than returning an empty frame.
    """
    def _clean(raw) -> list:
        items = [raw] if isinstance(raw, (int, float)) else (
            [p for p in str(raw).replace(";", ",").split(",") if p.strip()] if isinstance(raw, str)
            else list(raw))
        out = []
        for it in items:
            try:
                n = cast(it)
            except (TypeError, ValueError):
                continue
            if n > 0:
                out.append(n)
        return out

    if value is None:
        return _clean(default)
    out = _clean(value)
    return out or _clean(default)


# ----------------------------- indicators -----------------------------

def ind_ma(df: pd.DataFrame, periods=(5, 10, 20, 60)) -> pd.DataFrame:
    c = _col(df, "close")
    ns = _seq(periods, int, [5, 10, 20, 60])
    return pd.DataFrame({f"ma{n}": _ma(c, n) for n in ns}, index=df.index)


def ind_ema(df: pd.DataFrame, periods=(12, 26, 50)) -> pd.DataFrame:
    c = _col(df, "close")
    ns = _seq(periods, int, [12, 26, 50])
    return pd.DataFrame({f"ema{n}": _ema(c, n) for n in ns}, index=df.index)


def ind_boll(df: pd.DataFrame, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    c = _col(df, "close")
    mid = _ma(c, n)
    sd = c.rolling(n, min_periods=1).std(ddof=0)
    return pd.DataFrame({"boll_mid": mid, "boll_up": mid + k * sd, "boll_low": mid - k * sd}, index=df.index)


def ind_boll_ext(df: pd.DataFrame, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """布林带衍生: %B 位置 / 带宽 / ±1σ。带宽收敛是变盘前兆，%B 定位突破方向。"""
    c = _col(df, "close")
    mid = _ma(c, n)
    sd = c.rolling(n, min_periods=1).std(ddof=0)
    span = (2 * k * sd)
    pctb = (c - (mid - k * sd)) / span.replace(0, np.nan)
    bandwidth = span / mid.replace(0, np.nan)
    return pd.DataFrame({"boll_pctb": pctb, "boll_bw": bandwidth, "boll_1sd_up": mid + sd,
                         "boll_1sd_low": mid - sd}, index=df.index)


def ind_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, mid: int = 9) -> pd.DataFrame:
    c = _col(df, "close")
    dif = _ema(c, fast) - _ema(c, slow)
    dea = _ema(dif, mid)
    return pd.DataFrame({"macd_dif": dif, "macd_dea": dea, "macd": (dif - dea) * 2}, index=df.index)


def ind_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    high, low, close = _col(df, "high"), _col(df, "low"), _col(df, "close")
    llv = _llv(low, n)
    hhv = _hhv(high, n)
    rsv = (close - llv) / (hhv - llv).replace(0, np.nan) * 100
    rsv = rsv.fillna(50)
    k = _sma_cn(rsv, m1, 1)
    d = _sma_cn(k, m2, 1)
    j = 3 * k - 2 * d
    return pd.DataFrame({"kdj_k": k, "kdj_d": d, "kdj_j": j}, index=df.index)


def ind_rsi(df: pd.DataFrame, periods=(6, 12, 24)) -> pd.DataFrame:
    """相对强弱 (通达信 SMA 口径, 非 Wilder 平滑)。70/30 为超买超卖分界。"""
    c = _col(df, "close")
    diff = c.diff()
    up = diff.clip(lower=0)
    ad = diff.abs()
    out = {}
    for n in _seq(periods, int, [6, 12, 24]):
        out[f"rsi{n}"] = _sma_cn(up, n, 1) / _sma_cn(ad, n, 1).replace(0, np.nan) * 100
    return pd.DataFrame(out, index=df.index)


def ind_dmi(df: pd.DataFrame, n: int = 14, m: int = 6) -> pd.DataFrame:
    high, low = _col(df, "high"), _col(df, "low")
    hd = high.diff()
    ld = -low.diff()
    mtr = _sma_cn(_tr(df), n, 1)
    dmp = _sma_cn(pd.Series(np.where((hd > 0) & (hd > ld), hd, 0.0), index=df.index), n, 1)
    dmm = _sma_cn(pd.Series(np.where((ld > 0) & (ld > hd), ld, 0.0), index=df.index), n, 1)
    pdi = dmp * 100 / mtr.replace(0, np.nan)
    mdi = dmm * 100 / mtr.replace(0, np.nan)
    # A perfectly flat instrument has no directional movement at all, so the 0/0 below
    # is a real answer (ADX = 0, "no trend") rather than a missing one — without this it
    # degrades to NaN and the DMI rule reports 无数据 instead of 弃权.
    dx = 100 * (mdi - pdi).abs() / (mdi + pdi).where(mdi + pdi > 0, np.nan)
    dx = dx.fillna(0.0)
    adx = _sma_cn(dx, m, 1)
    adxr = (adx + adx.shift(m)) / 2
    return pd.DataFrame({"dmi_pdi": pdi, "dmi_mdi": mdi, "dmi_adx": adx, "dmi_adxr": adxr}, index=df.index)


def ind_atr(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """真实波幅 + 占价格百分比。atr_pct 是跨品种可比的风险度量，atr 本身不可比。"""
    close = _col(df, "close")
    atr = _sma_cn(_tr(df), n, 1)
    return pd.DataFrame({"atr": atr, "atr_pct": atr / close.replace(0, np.nan) * 100}, index=df.index)


def ind_obv(df: pd.DataFrame) -> pd.DataFrame:
    c, v = _col(df, "close"), _col(df, "volume")
    sign = np.sign(c.diff()).fillna(0)
    return pd.DataFrame({"obv": (sign * v).cumsum()}, index=df.index)


def ind_sar(df: pd.DataFrame, step: float = 0.02, maxaf: float = 0.2) -> pd.DataFrame:
    high = _col(df, "high").to_numpy()
    low = _col(df, "low").to_numpy()
    n = len(df)
    sar = np.zeros(n)
    if n == 0:
        return pd.DataFrame({"sar": sar}, index=df.index)
    bull = True
    af = step
    ep = high[0]
    sar[0] = low[0]
    for i in range(1, n):
        prev = sar[i - 1]
        sar[i] = prev + af * (ep - prev)
        if bull:
            sar[i] = min(sar[i], low[i - 1], low[i - 2] if i >= 2 else low[i - 1])
            if high[i] > ep:
                ep = high[i]
                af = min(af + step, maxaf)
            if low[i] < sar[i]:
                bull = False
                sar[i] = ep
                ep = low[i]
                af = step
        else:
            sar[i] = max(sar[i], high[i - 1], high[i - 2] if i >= 2 else high[i - 1])
            if low[i] < ep:
                ep = low[i]
                af = min(af + step, maxaf)
            if high[i] > sar[i]:
                bull = True
                sar[i] = ep
                ep = high[i]
                af = step
    return pd.DataFrame({"sar": sar}, index=df.index)


def ind_cci(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    tp = (_col(df, "high") + _col(df, "low") + _col(df, "close")) / 3
    ma_tp = _ma(tp, n)
    md = (tp - ma_tp).abs().rolling(n, min_periods=1).mean()
    return pd.DataFrame({"cci": (tp - ma_tp) / (0.015 * md).replace(0, np.nan)}, index=df.index)


def ind_wr(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    high, low, close = _col(df, "high"), _col(df, "low"), _col(df, "close")
    hhv, llv = _hhv(high, n), _llv(low, n)
    return pd.DataFrame({"wr": 100 * (hhv - close) / (hhv - llv).replace(0, np.nan)}, index=df.index)


def ind_bbi(df: pd.DataFrame) -> pd.DataFrame:
    c = _col(df, "close")
    bbi = (_ma(c, 3) + _ma(c, 6) + _ma(c, 12) + _ma(c, 24)) / 4
    return pd.DataFrame({"bbi": bbi}, index=df.index)


def ind_donchian(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    up = _hhv(_col(df, "high"), n)
    low = _llv(_col(df, "low"), n)
    return pd.DataFrame({"don_up": up, "don_low": low, "don_mid": (up + low) / 2}, index=df.index)


def ind_keltner(df: pd.DataFrame, n: int = 20, k: float = 1.5) -> pd.DataFrame:
    mid = _ema(_col(df, "close"), n)
    atr = _sma_cn(_tr(df), n, 1)
    return pd.DataFrame({"kelt_mid": mid, "kelt_up": mid + k * atr,
                         "kelt_low": mid - k * atr}, index=df.index)


def ind_trix(df: pd.DataFrame, n: int = 12, m: int = 9) -> pd.DataFrame:
    c = _col(df, "close")
    tr = _ema(_ema(_ema(c, n), n), n)
    trix = (tr - tr.shift(1)) / tr.shift(1).replace(0, np.nan) * 100
    return pd.DataFrame({"trix": trix, "trix_ma": _ma(trix, m)}, index=df.index)


def ind_aroon(df: pd.DataFrame, n: int = 25) -> pd.DataFrame:
    high, low = _col(df, "high"), _col(df, "low")
    since_hi = high.rolling(n, min_periods=1).apply(lambda x: n - 1 - int(np.argmax(x)), raw=True)
    since_lo = low.rolling(n, min_periods=1).apply(lambda x: n - 1 - int(np.argmin(x)), raw=True)
    up = (n - since_hi) / n * 100
    down = (n - since_lo) / n * 100
    return pd.DataFrame({"aroon_up": up, "aroon_down": down, "aroon_osc": up - down}, index=df.index)


def ind_mavol(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    v = _col(df, "volume")
    return pd.DataFrame({"mavol": _ma(v, n), "vol": v}, index=df.index)


def ind_skdj(df: pd.DataFrame, n: int = 9, m: int = 3) -> pd.DataFrame:
    high, low, close = _col(df, "high"), _col(df, "low"), _col(df, "close")
    lowv, highv = _llv(low, n), _hhv(high, n)
    rsv = _ema((close - lowv) / (highv - lowv).replace(0, np.nan) * 100, m)
    k = _ema(rsv, m)
    d = _ma(k, m)
    return pd.DataFrame({"skdj_k": k, "skdj_d": d}, index=df.index)


def ind_roc(df: pd.DataFrame, n: int = 12, m: int = 6) -> pd.DataFrame:
    c = _col(df, "close")
    roc = 100 * (c - c.shift(n)) / c.shift(n).replace(0, np.nan)
    return pd.DataFrame({"roc": roc, "roc_ma": _ma(roc, m)}, index=df.index)


def ind_mtm(df: pd.DataFrame, n: int = 12, m: int = 6) -> pd.DataFrame:
    c = _col(df, "close")
    mtm = c - c.shift(n)
    return pd.DataFrame({"mtm": mtm, "mtm_ma": _ma(mtm, m)}, index=df.index)


def ind_bias(df: pd.DataFrame, periods=(6, 12, 24)) -> pd.DataFrame:
    """乖离率: 收盘价对均线的偏离 %。正负对称, ±10% 附近常是短线极值区。"""
    c = _col(df, "close")
    out = {}
    for n in _seq(periods, int, [6, 12, 24]):
        ma = _ma(c, n)
        out[f"bias{n}"] = 100 * (c - ma) / ma.replace(0, np.nan)
    return pd.DataFrame(out, index=df.index)


def ind_psy(df: pd.DataFrame, n: int = 12, m: int = 6) -> pd.DataFrame:
    c = _col(df, "close")
    up = (c > c.shift(1)).astype(float)
    psy = up.rolling(n, min_periods=1).mean() * 100
    return pd.DataFrame({"psy": psy, "psy_ma": _ma(psy, m)}, index=df.index)


def ind_cr(df: pd.DataFrame, n: int = 26) -> pd.DataFrame:
    high, low = _col(df, "high"), _col(df, "low")
    mid = (_col(df, "high") + _col(df, "low")).shift(1) / 2
    up = (high - mid).clip(lower=0).rolling(n, min_periods=1).sum()
    dn = (mid - low).clip(lower=0).rolling(n, min_periods=1).sum()
    cr = up / dn.replace(0, np.nan) * 200
    return pd.DataFrame({"cr": cr, "cr_ma5": _ma(cr, 5), "cr_ma10": _ma(cr, 10)}, index=df.index)


def ind_vr(df: pd.DataFrame, n: int = 26) -> pd.DataFrame:
    c, v = _col(df, "close"), _col(df, "volume")
    pc = c.shift(1)
    av = pd.Series(np.where(c > pc, v, 0.0), index=df.index).rolling(n, min_periods=1).sum()
    bv = pd.Series(np.where(c < pc, v, 0.0), index=df.index).rolling(n, min_periods=1).sum()
    cv = pd.Series(np.where(c == pc, v, 0.0), index=df.index).rolling(n, min_periods=1).sum()
    vr = (av + cv / 2) / (bv + cv / 2).replace(0, np.nan) * 100
    return pd.DataFrame({"vr": vr, "vr_ma": _ma(vr, 6)}, index=df.index)


def ind_mfi(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    tp = (_col(df, "high") + _col(df, "low") + _col(df, "close")) / 3
    mf = tp * _col(df, "volume")
    d = tp.diff()
    pos = pd.Series(np.where(d > 0, mf, 0.0), index=df.index).rolling(n, min_periods=1).sum()
    neg = pd.Series(np.where(d < 0, mf, 0.0), index=df.index).rolling(n, min_periods=1).sum()
    mr = pos / neg.replace(0, np.nan)
    return pd.DataFrame({"mfi": 100 - 100 / (1 + mr)}, index=df.index)


def ind_emv(df: pd.DataFrame, n: int = 14, m: int = 9) -> pd.DataFrame:
    high, low, vol = _col(df, "high"), _col(df, "low"), _col(df, "volume")
    mid = 100 * (high + low - (high.shift(1) + low.shift(1))) / (high + low).replace(0, np.nan)
    bro = vol / (high - low).replace(0, np.nan)
    rng_ma = _ma(high - low, n)
    emv = _ma(mid / bro.replace(0, np.nan) * (high - low) / rng_ma.replace(0, np.nan), n)
    return pd.DataFrame({"emv": emv, "emv_ma": _ma(emv, m)}, index=df.index)


def ind_qrr(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    v = _col(df, "volume")
    return pd.DataFrame({"qrr": v / _ma(v, n).replace(0, np.nan)}, index=df.index)


def ind_asi(df: pd.DataFrame) -> pd.DataFrame:
    o, high, low, close = _col(df, "open"), _col(df, "high"), _col(df, "low"), _col(df, "close")
    lc = close.shift(1)
    aa = (high - lc).abs()
    bb = (low - lc).abs()
    cc = (high - low.shift(1)).abs()
    dd = (lc - o.shift(1)).abs()
    r = pd.Series(np.nan, index=df.index)
    r = np.where((aa >= bb) & (aa >= cc), aa + bb / 2 + dd / 4,
                 np.where((bb >= cc) & (bb >= aa), bb + aa / 2 + dd / 4, cc + dd / 4))
    x = close - lc + (close - o) / 2 + lc - o.shift(1)
    k = pd.concat([aa, bb, cc], axis=1).max(axis=1)
    si = 16 * x / pd.Series(r, index=df.index).replace(0, np.nan) * k
    cum = si.fillna(0).cumsum()
    return pd.DataFrame({"asi": cum, "asit": _ma(cum, 10)}, index=df.index)


def ind_hv(df: pd.DataFrame, n: int = 24) -> pd.DataFrame:
    """年化已实现波动: N 日对数收益标准差 × √252.

    Non-positive closes are masked out first: ``log(0)`` is -inf and ``log(0/0)`` is NaN,
    and one bad bar would otherwise poison the whole rolling window with warnings.
    """
    c = _col(df, "close")
    c = c.where(c > 0)
    lr = np.log(c / c.shift(1))
    hv = lr.rolling(n, min_periods=2).std(ddof=0) * math.sqrt(252) * 100
    return pd.DataFrame({"hv": hv}, index=df.index)


def ind_oi(df: pd.DataFrame) -> pd.DataFrame:
    """Open interest passthrough (futures); empty if absent."""
    if "oi" in df.columns:
        return pd.DataFrame({"oi": df["oi"].astype(float)}, index=df.index)
    return pd.DataFrame(index=df.index)


def ind_turnover(df: pd.DataFrame) -> pd.DataFrame:
    """Stock volume副图 substitute for OI: 换手率/成交额."""
    out = {}
    if "turnover_rate" in df.columns:
        out["turnover"] = df["turnover_rate"].astype(float)
    if "amount" in df.columns:
        out["amount"] = df["amount"].astype(float)
    return pd.DataFrame(out, index=df.index)


# ---- 量价类 (第二轮新增) ----
# These lean on volume + price together, which is where ETF / 可转债 analysis differs
# most from index analysis: 折溢价与流动性本身就是信号的一部分。

def ind_vwap(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """成交量加权均价 VWAP。

    优先用 成交额/成交量 (真实均价); 缺 成交额 时退回 (H+L+C)/3 加权。
    样本内累计 (累计自最新 ``n`` 根的起点) 与滚动 ``n`` 日两条线: 累计线是机构的
    持仓成本参考, 滚动线是短线多空分界。
    """
    close = _col(df, "close")
    vol = _col(df, "volume")
    amount = _opt_col(df, "amount")
    if amount is not None:
        pv = amount
    else:
        pv = (_col(df, "high") + _col(df, "low") + close) / 3 * vol
    pv_sum = pv.rolling(n, min_periods=1).sum()
    v_sum = vol.rolling(n, min_periods=1).sum()
    rolling = pv_sum / v_sum.replace(0, np.nan)
    # 累计线以窗口最后一根为锚点向前累加 (rolling 反向求和), 避免依赖序列起点。
    cum = pv[::-1].cumsum()[::-1].shift(-(n - 1))
    cum_v = vol[::-1].cumsum()[::-1].shift(-(n - 1))
    return pd.DataFrame({"vwap": rolling, "vwap_cum": cum / cum_v.replace(0, np.nan),
                         "vwap_dev": 100 * (close / rolling.replace(0, np.nan) - 1)}, index=df.index)


def ind_vwma(df: pd.DataFrame, periods=(5, 10, 20)) -> pd.DataFrame:
    """成交量加权均线: 放量日的收盘价权重更高, 比等权 MA 更贴近持仓成本。"""
    close = _col(df, "close")
    vol = _col(df, "volume")
    pv = close * vol
    out = {}
    for n in _seq(periods, int, [5, 10, 20]):
        denom = vol.rolling(n, min_periods=1).sum()
        out[f"vwma{n}"] = pv.rolling(n, min_periods=1).sum() / denom.replace(0, np.nan)
    return pd.DataFrame(out, index=df.index)


def ind_pvt(df: pd.DataFrame) -> pd.DataFrame:
    """量价趋势 PVT: Σ(涨跌幅 × 成交量)。OBV 的涨跌幅加权版本, 数值量级可比成交量。"""
    close = _col(df, "close")
    vol = _col(df, "volume")
    chg = close.pct_change().fillna(0.0)
    return pd.DataFrame({"pvt": (chg * vol).cumsum(), "pvt_ma": _ma((chg * vol).cumsum(), 14)},
                        index=df.index)


def ind_std(df: pd.DataFrame, periods=(20,)) -> pd.DataFrame:
    """收盘价标准差 — 绝对波动。与 hv (年化对数收益波动) 互为快慢视角。"""
    close = _col(df, "close")
    out = {}
    for n in _seq(periods, int, [20]):
        sd = close.rolling(n, min_periods=1).std(ddof=0)
        out[f"std{n}"] = sd
        out[f"std{n}_pct"] = sd / _ma(close, n).replace(0, np.nan) * 100
    return pd.DataFrame(out, index=df.index)


def ind_brar(df: pd.DataFrame, n: int = 26) -> pd.DataFrame:
    """情绪指标 BR/AR (通达信 BRAR)。

    ``mid`` = (O+C+H+L)/4, ``ma_mid`` = mid 的 n 日均线;
    ``BR`` = Σ max(C−ma_mid,0) / Σ max(ma_mid−C,0) × 100 —— n 日多方/空方累计力度;
    ``AR`` = Σ max(H−mid,0) / Σ max(mid−L,0) × 100 —— 当日多方/空方力度。
    BR>100 偏多, AR 是 BR 的日内版本, 两者背离说明趋势与短线动能相反。
    """
    open_ = _col(df, "open")
    high, low, close = _col(df, "high"), _col(df, "low"), _col(df, "close")
    mid = (open_ + high + low + close) / 4
    mid_ma = _ma(mid, n)
    bull = (close - mid_ma).clip(lower=0).rolling(n, min_periods=1).sum()
    bear = (mid_ma - close).clip(lower=0).rolling(n, min_periods=1).sum()
    a_up = (high - mid).clip(lower=0).rolling(n, min_periods=1).sum()
    a_dn = (mid - low).clip(lower=0).rolling(n, min_periods=1).sum()
    return pd.DataFrame({"brar_br": _ratio(bull, bear), "brar_ar": _ratio(a_up, a_dn),
                         "brar_br_ma": _ma(_ratio(bull, bear), 6)}, index=df.index)


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """``100 × num / den``, saturating at 100 when the denominator is empty.

    A window with *no* bars on the losing side is complete dominance by the winning
    side, i.e. an infinite ratio. Plain division would give 0/0 → NaN, which drops the
    column for exactly the most one-sided names — the opposite of what the ratio is for.
    Saturating at 100 reads as 强烈偏多; only a genuinely flat window (both sides zero)
    stays NaN.
    """
    return (100 * num / den.replace(0, np.nan)).where(
        den > 0, 100 * num.gt(0).astype(float).replace(0.0, np.nan)
    )


def ind_dpo(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """去趋势价格振荡 DPO: 收盘价 − n/2+1 日前的移动均线。

    有意滞后 n/2 根, 使历史极值与当前价直接可比 (dpo_up/dpo_dn 即超买超卖线)。
    """
    close = _col(df, "close")
    shift = n // 2 + 1
    dpo = close.shift(shift) - _ma(close, n)
    prev = dpo.shift(1)
    return pd.DataFrame({"dpo": dpo, "dpo_up": prev.rolling(n, min_periods=1).max(),
                         "dpo_dn": prev.rolling(n, min_periods=1).min()}, index=df.index)


def ind_cmo(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """钱龙动量 CMO (Chande): (上涨日之和 − 下跌日之和) / (两者之和) × 100。

    相对 RSI 更敏感, ±50 常作为超买超卖参考。
    """
    close = _col(df, "close")
    diff = close.diff()
    up = diff.clip(lower=0).rolling(n, min_periods=1).sum()
    dn = (-diff.clip(upper=0)).rolling(n, min_periods=1).sum()
    cmo = 100 * (up - dn) / (up + dn).replace(0, np.nan)
    return pd.DataFrame({"cmo": cmo, "cmo_ma": _ma(cmo, 6)}, index=df.index)


def ind_ma_align(df: pd.DataFrame, periods=(5, 10, 20, 60)) -> pd.DataFrame:
    """均线多空排列强度。

    ``ma_align`` = 处于多头排列的均线对数 / 全部均线对 × 100 (100 = 完全多头排列,
    0 = 完全空头排列); ``ma_ma_gap`` = 最长均线与收盘价的乖离 %。
    """
    close = _col(df, "close")
    ns = sorted(set(_seq(periods, int, [5, 10, 20, 60])))
    mas = [_ma(close, n) for n in ns]
    up = pd.Series(0.0, index=df.index)
    total = 0
    for i in range(len(mas)):
        for j in range(i + 1, len(mas)):
            total += 1
            up = up + (mas[i] >= mas[j]).astype(float)
    align = 100 * up / total if total else pd.Series(50.0, index=df.index)
    longest = mas[-1]
    return pd.DataFrame({"ma_align": align,
                         "ma_ma_gap": 100 * (close - longest) / longest.replace(0, np.nan)},
                        index=df.index)


def ind_mfi_ext(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """资金流量 MFI 的价格位置视角: MFI − 50 与 MFI/成交量背离。

    MFI 已在 80/20 划分超买超卖; 这里给出以零轴为基准的动量形式, 便于与 MACD 同轴比较。
    """
    frame = ind_mfi(df, n)
    mfi = frame["mfi"]
    return pd.DataFrame({"mfi_bias": mfi - 50, "mfi_ma": _ma(mfi, 6)}, index=df.index)



INDICATORS: dict[str, Callable[..., pd.DataFrame]] = {
    # 趋势
    "ma": ind_ma, "ema": ind_ema, "ma_align": ind_ma_align, "bbi": ind_bbi,
    "sar": ind_sar, "donchian": ind_donchian, "keltner": ind_keltner, "aroon": ind_aroon,
    "dmi": ind_dmi,
    # 震荡 / 通道
    "boll": ind_boll, "boll_ext": ind_boll_ext, "kdj": ind_kdj, "skdj": ind_skdj,
    "rsi": ind_rsi, "wr": ind_wr, "cci": ind_cci, "cmo": ind_cmo, "dpo": ind_dpo,
    "psy": ind_psy,
    # 动量
    "macd": ind_macd, "trix": ind_trix, "roc": ind_roc, "mtm": ind_mtm, "bias": ind_bias,
    # 量价 / 资金
    "mavol": ind_mavol, "obv": ind_obv, "pvt": ind_pvt, "vwap": ind_vwap,
    "vwma": ind_vwma, "qrr": ind_qrr, "vr": ind_vr, "cr": ind_cr, "brar": ind_brar,
    "mfi": ind_mfi, "mfi_ext": ind_mfi_ext, "emv": ind_emv, "std": ind_std,
    # 波动 / 其他
    "atr": ind_atr, "hv": ind_hv, "asi": ind_asi, "oi": ind_oi, "turnover": ind_turnover,
}

ALIASES: dict[str, str] = {
    "均线": "ma", "指数均线": "ema", "布林": "boll", "布林带": "boll", "macd": "macd",
    "kdj": "kdj", "随机指标": "kdj", "rsi": "rsi", "相对强弱": "rsi", "dmi": "dmi",
    "趋向指标": "dmi", "atr": "atr", "真实波幅": "atr", "obv": "obv", "能量潮": "obv",
    "sar": "sar", "抛物线": "sar", "cci": "cci", "wr": "wr", "威廉": "wr", "bbi": "bbi",
    "唐奇安": "donchian", "donchian": "donchian", "肯特纳": "keltner", "keltner": "keltner",
    "trix": "trix", "aroon": "aroon", "阿隆": "aroon", "vol": "mavol", "成交量": "mavol",
    "skdj": "skdj", "慢速随机": "skdj", "roc": "roc", "变动率": "roc", "mtm": "mtm",
    "动量": "mtm", "bias": "bias", "乖离率": "bias", "psy": "psy", "心理线": "psy",
    "cr": "cr", "vr": "vr", "mfi": "mfi", "资金流量": "mfi", "emv": "emv", "qrr": "qrr",
    "量比": "qrr", "asi": "asi", "hv": "hv", "历史波动率": "hv", "oi": "oi", "持仓量": "oi",
    "换手": "turnover", "换手率": "turnover",
    # 第二轮新增
    "vwap": "vwap", "均价": "vwap", "vwma": "vwma", "量价均线": "vwma",
    "pvt": "pvt", "量价趋势": "pvt", "std": "std", "标准差": "std",
    "brar": "brar", "情绪指标": "brar", "dpo": "dpo", "去趋势": "dpo",
    "cmo": "cmo", "钱龙动量": "cmo", "排列": "ma_align", "多头排列": "ma_align",
    "mfi_ext": "mfi_ext", "资金流向": "mfi_ext",
}

DEFAULT_INDICATORS = ["ma", "macd", "kdj", "rsi", "boll", "mavol"]

#: Bar frequencies the API accepts. Daily is stored; weekly/monthly are resampled on read.
FREQS: tuple[str, ...] = ("daily", "weekly", "monthly")

#: How many raw daily bars one weekly/monthly bar needs, used to size the pre-resample
#: window so a "1y" weekly chart still covers a year of trading days.
FREQ_BARS: dict[str, int] = {"daily": 1, "weekly": 5, "monthly": 21}


#: key -> {label, group, pane, desc, params, needs}
#:
#: ``pane`` drives the chart layout: ``main`` indicators overlay the price grid, ``sub``
#: ones get their own sub-grid. ``params`` documents the keyword arguments
#: ``compute(..., params=...)`` accepts, so the UI can render an editor without a
#: second source of truth. ``needs`` lists optional feed columns the indicator degrades
#: without (``amount``/``turnover_rate``) — the UI greys out those choices for feeds
#: that don't carry them (e.g. index bars).
INDICATOR_META: dict[str, dict] = {
    "ma": {"label": "均线", "group": "趋势", "pane": "main",
           "desc": "收盘价的简单移动平均。5/10/20/60 日分别对应周线、月线、季线、年线口径；"
                   "价格站上全部均线为多头排列。",
           "params": {"periods": [5, 10, 20, 60]}, "columns": ["ma5", "ma10", "ma20", "ma60"]},
    "ema": {"label": "指数均线", "group": "趋势", "pane": "main",
            "desc": "EMA(X,N) = 2/(N+1) × 前值 + (1−2/(N+1)) × 现值，权重给近期价格，适合更快跟随。",
            "params": {"periods": [12, 26, 50]}, "columns": ["ema12", "ema26", "ema50"]},
    "ma_align": {"label": "均线排列", "group": "趋势", "pane": "sub",
                 "desc": "多头排列的均线对占比 0-100（100=完全多头，0=完全空头）+ 最长均线乖离率%。",
                 "params": {"periods": [5, 10, 20, 60]},
                 "columns": ["ma_align", "ma_ma_gap"]},
    "bbi": {"label": "多空指标", "group": "趋势", "pane": "main",
            "desc": "BBI = (MA3+MA6+MA12+MA24)/4，多空分界线；价在 BBI 之上偏多。",
            "params": {}, "columns": ["bbi"]},
    "sar": {"label": "抛物线转向", "group": "趋势", "pane": "main",
            "desc": "SAR 点位随趋势推进加速翻转，止损/跟踪位；点翻转为方向反转信号。",
            "params": {"step": 0.02, "maxaf": 0.2}, "columns": ["sar"]},
    "donchian": {"label": "唐奇安通道", "group": "趋势", "pane": "main",
                 "desc": "N 日最高/最低价构成的突破通道，中轨为上下轨均值。海龟式突破系统的基础。",
                 "params": {"n": 20}, "columns": ["don_up", "don_low", "don_mid"]},
    "keltner": {"label": "肯特纳通道", "group": "趋势", "pane": "main",
                "desc": "EMA(N) ± k×ATR。相对布林带用真实波幅定宽，对跳空更宽容。",
                "params": {"n": 20, "k": 1.5}, "columns": ["kelt_mid", "kelt_up", "kelt_low"]},
    "aroon": {"label": "阿隆指标", "group": "趋势", "pane": "sub",
              "desc": "N 日内最高/最低出现的位置归一化到 0-100；Aroon Osc > 0 表示高点比低点新。",
              "params": {"n": 25}, "columns": ["aroon_up", "aroon_down", "aroon_osc"]},
    "dmi": {"label": "趋向指标 DMI", "group": "趋势", "pane": "sub",
            "desc": "+DI/−DI 相对强弱与 ADX 趋势强度。+DI 上穿 −DI 为金叉，ADX>25 趋势成立。",
            "params": {"n": 14, "m": 6},
            "columns": ["dmi_pdi", "dmi_mdi", "dmi_adx", "dmi_adxr"]},
    "boll": {"label": "布林带", "group": "震荡", "pane": "main",
             "desc": "中轨 MA(N)，上下轨 ±kσ。触轨为极值区；带宽收敛常预示变盘。",
             "params": {"n": 20, "k": 2.0}, "columns": ["boll_mid", "boll_up", "boll_low"]},
    "boll_ext": {"label": "布林带衍生", "group": "震荡", "pane": "sub",
                 "desc": "%B 定位价格在带内的相对位置（0=下轨，1=上轨）+ 带宽收敛度 + ±1σ。",
                 "params": {"n": 20, "k": 2.0},
                 "columns": ["boll_pctb", "boll_bw", "boll_1sd_up", "boll_1sd_low"]},
    "kdj": {"label": "随机指标 KDJ", "group": "震荡", "pane": "sub",
            "desc": "RSV 经 SMA(3,1) 平滑得 K、再得 D，J=3K−2D。K/D 在 20/80 为超买超卖；"
                    "低位 K 上穿 D 为金叉。",
            "params": {"n": 9, "m1": 3, "m2": 3}, "columns": ["kdj_k", "kdj_d", "kdj_j"]},
    "skdj": {"label": "慢速随机 SKDJ", "group": "震荡", "pane": "sub",
             "desc": "对 RSV 做两次 EMA 平滑的随机指标，波动小于 KDJ，钝化更少。",
             "params": {"n": 9, "m": 3}, "columns": ["skdj_k", "skdj_d"]},
    "rsi": {"label": "相对强弱 RSI", "group": "震荡", "pane": "sub",
            "desc": "SMA(N) 口径的涨跌力量对比 ×100。>70 超买、<30 超卖；顶背离/底背离是主要反转线索。",
            "params": {"periods": [6, 12, 24]}, "columns": ["rsi6", "rsi12", "rsi24"]},
    "wr": {"label": "威廉指标 WR", "group": "震荡", "pane": "sub",
           "desc": "收盘价在 N 日区间内的位置，0=最高、100=最低，与 RSI 互补。",
           "params": {"n": 10}, "columns": ["wr"]},
    "cci": {"label": "顺势指标 CCI", "group": "震荡", "pane": "sub",
            "desc": "典型价对 N 日均价的偏离 / 0.015×平均绝对偏差。>100 超买、<−100 超卖。",
            "params": {"n": 14}, "columns": ["cci"]},
    "cmo": {"label": "钱龙动量 CMO", "group": "震荡", "pane": "sub",
            "desc": "Chande 动量：N 日涨跌幅之和 − 跌幅之和，占比 ×100。比 RSI 更敏感，±50 为参考区。",
            "params": {"n": 14}, "columns": ["cmo", "cmo_ma"]},
    "dpo": {"label": "去趋势振荡 DPO", "group": "震荡", "pane": "sub",
            "desc": "收盘价 − N/2+1 日前的 MA(N)，有意滞后使历史极值可直接与现价比较。",
            "params": {"n": 20}, "columns": ["dpo", "dpo_up", "dpo_dn"]},
    "psy": {"label": "心理线 PSY", "group": "震荡", "pane": "sub",
            "desc": "N 日内上涨天数占比 ×100。>80 人气过热、<20 人气低迷。",
            "params": {"n": 12, "m": 6}, "columns": ["psy", "psy_ma"]},
    "macd": {"label": "MACD", "group": "动量", "pane": "sub",
             "desc": "DIF = EMA(fast)−EMA(slow)，DEA = SMA(DIF, mid)，柱 = 2×(DIF−DEA)。"
                     "DIF 上穿 DEA 金叉、下穿死叉；柱体反映动量加速度。",
             "params": {"fast": 12, "slow": 26, "mid": 9},
             "columns": ["macd_dif", "macd_dea", "macd"]},
    "trix": {"label": "三重指数平滑", "group": "动量", "pane": "sub",
             "desc": "收盘价三重 EMA 的一阶导数百分比，长期趋势动量，过滤短噪声。",
             "params": {"n": 12, "m": 9}, "columns": ["trix", "trix_ma"]},
    "roc": {"label": "变动率 ROC", "group": "动量", "pane": "sub",
            "desc": "N 日涨跌幅 %，衡量价格相对 N 日前的位移速度。",
            "params": {"n": 12, "m": 6}, "columns": ["roc", "roc_ma"]},
    "mtm": {"label": "动量 MTM", "group": "动量", "pane": "sub",
            "desc": "收盘价 − N 日前收盘价（绝对价差），ROC 的价格单位版本。",
            "params": {"n": 12, "m": 6}, "columns": ["mtm", "mtm_ma"]},
    "bias": {"label": "乖离率 BIAS", "group": "动量", "pane": "sub",
             "desc": "收盘价对 N 日均线的偏离 %。正乖离过大为超买，负乖离过大为超卖。",
             "params": {"periods": [6, 12, 24]}, "columns": ["bias6", "bias12", "bias24"]},
    "mavol": {"label": "成交量均线", "group": "量价", "pane": "sub",
              "desc": "成交量及其 N 日均量，用于识别放量/缩量。",
              "params": {"n": 5}, "columns": ["mavol", "vol"]},
    "obv": {"label": "能量潮 OBV", "group": "量价", "pane": "sub",
            "desc": "按涨跌方向累加成交量，与价格趋势互相验证。",
            "params": {}, "columns": ["obv"]},
    "pvt": {"label": "量价趋势 PVT", "group": "量价", "pane": "sub",
            "desc": "Σ(当日涨跌幅 × 成交量)，OBV 的涨跌幅加权版本，量级可直接与成交量比较。",
            "params": {}, "columns": ["pvt", "pvt_ma"]},
    "vwap": {"label": "成交量加权均价 VWAP", "group": "量价", "pane": "main",
             "desc": "成交额/成交量（缺成交额时用 (H+L+C)/3 兜底）。滚动 N 日均价线 + 样本内累计"
                     "均价线，累计线是机构持仓成本参考。",
             "params": {"n": 20}, "columns": ["vwap", "vwap_cum", "vwap_dev"], "needs": ["amount"]},
    "vwma": {"label": "成交量加权均线", "group": "量价", "pane": "main",
             "desc": "Σ(收盘价×成交量)/Σ成交量，放量收盘权重更高，更贴近真实持仓成本。",
             "params": {"periods": [5, 10, 20]}, "columns": ["vwma5", "vwma10", "vwma20"]},
    "qrr": {"label": "量比", "group": "量价", "pane": "sub",
            "desc": "当日成交量 / N 日均量，>1.5 放量、<0.7 缩量。",
            "params": {"n": 5}, "columns": ["qrr"]},
    "vr": {"label": "成交量比率 VR", "group": "量价", "pane": "sub",
           "desc": "(上涨日量 + 平盘量/2) / (下跌日量 + 平盘量/2) × 100，26 日窗口。",
           "params": {"n": 26}, "columns": ["vr", "vr_ma"]},
    "cr": {"label": "能量比率 CR", "group": "量价", "pane": "sub",
           "desc": "以 N 日均价为轴的多空力量对比 ×200，>150 偏多、<50 偏空。",
           "params": {"n": 26}, "columns": ["cr", "cr_ma5", "cr_ma10"]},
    "brar": {"label": "情绪指标 BRAR", "group": "量价", "pane": "sub",
             "desc": "BR = N 日多空累计力度比（>100 偏多），AR = 当日多空力度比。两者背离说明"
                     "趋势与短线动能相反。",
             "params": {"n": 26}, "columns": ["brar_br", "brar_ar", "brar_br_ma"]},
    "mfi": {"label": "资金流量 MFI", "group": "量价", "pane": "sub",
            "desc": "典型价×成交量的资金流，>80 超买、<20 超卖。比 RSI 多一个成交量维度。",
            "params": {"n": 14}, "columns": ["mfi"]},
    "mfi_ext": {"label": "资金流动量", "group": "量价", "pane": "sub",
                "desc": "MFI − 50 的零轴形式 + 均线，便于与 MACD 同轴对比。",
                "params": {"n": 14}, "columns": ["mfi_bias", "mfi_ma"]},
    "emv": {"label": "简易波动 EMV", "group": "量价", "pane": "sub",
            "desc": "量价配合度：价差扩大且放量为正，缩量则为负，识别突破有效性。",
            "params": {"n": 14, "m": 9}, "columns": ["emv", "emv_ma"]},
    "std": {"label": "价格标准差", "group": "波动", "pane": "sub",
            "desc": "收盘价 N 日标准差（绝对值 + 占均线 %），横截面比较个股波动水平。",
            "params": {"periods": [20]}, "columns": ["std20", "std20_pct"]},
    "atr": {"label": "真实波幅 ATR", "group": "波动", "pane": "sub",
            "desc": "N 日真实波幅均值及其占价格百分比。atr_pct 跨品种可比，用于仓位与止损。",
            "params": {"n": 14}, "columns": ["atr", "atr_pct"]},
    "hv": {"label": "历史波动率", "group": "波动", "pane": "sub",
           "desc": "N 日对数收益标准差年化（×√252）。衡量已实现波动，与期权隐含波动对应。",
           "params": {"n": 24}, "columns": ["hv"]},
    "asi": {"label": "振动升降指标 ASI", "group": "趋势", "pane": "sub",
            "desc": "综合开高低收与前收的距离，累积成线并给出 10 日均线。",
            "params": {}, "columns": ["asi", "asit"]},
    "oi": {"label": "持仓量", "group": "衍生品", "pane": "sub",
           "desc": "期货持仓量直传；无持仓量数据源时该指标不出值。",
           "params": {}, "columns": ["oi"], "needs": ["oi"]},
    "turnover": {"label": "换手率/成交额", "group": "量价", "pane": "sub",
                 "desc": "个股换手率与成交额直传，用于替代期货持仓量观察流动性。",
                 "params": {}, "columns": ["turnover", "amount"],
                 "needs": ["turnover_rate", "amount"]},
}


def catalog(groups: list[str] | None = None) -> list[dict]:
    """Indicator catalog for the UI: label, group, pane, formula text, parameters.

    Entries are ordered by ``group`` then label so the 指标说明 panel and the chart's
    indicator picker share one stable ordering. ``groups`` filters by category.
    """
    want = set(groups) if groups else None
    out = []
    for key, meta in INDICATOR_META.items():
        if key not in INDICATORS:
            continue
        if want and meta.get("group") not in want:
            continue
        out.append({"key": key, "label": meta["label"], "group": meta["group"],
                    "pane": meta.get("pane", "sub"), "desc": meta["desc"],
                    "params": meta.get("params", {}), "columns": meta.get("columns", []),
                    "needs": meta.get("needs", []), "aliases": _aliases_of(key)})
    order = {"趋势": 0, "震荡": 1, "动量": 2, "量价": 3, "波动": 4, "衍生品": 5}
    out.sort(key=lambda m: (order.get(m["group"], 9), m["label"]))
    return out


def _aliases_of(key: str) -> list[str]:
    return sorted(a for a, target in ALIASES.items() if target == key and a != key)


def _resolve(name: str) -> str:
    n = name.strip().lower()
    return ALIASES.get(n, ALIASES.get(name.strip(), n))


def compute(df: pd.DataFrame, names: list[str] | None = None,
            params: dict[str, dict] | None = None) -> dict[str, pd.DataFrame]:
    """Compute requested indicators over an OHLCV frame.

    Unknown names are skipped, and an indicator that raises for any reason (missing
    column, bad parameter) is dropped rather than failing the whole response — a
    partial indicator set is more useful to the page than an error.
    """
    names = names or DEFAULT_INDICATORS
    out: dict[str, pd.DataFrame] = {}
    for raw in names:
        key = _resolve(raw)
        fn = INDICATORS.get(key)
        if fn is None:
            continue
        kwargs = (params or {}).get(key) or (params or {}).get(_resolve(raw)) or {}
        try:
            res = fn(df, **kwargs) if kwargs else fn(df)
            if isinstance(res, pd.DataFrame) and not res.empty:
                out[key] = res
        except Exception:  # noqa: BLE001 - one bad indicator must not break the payload
            continue
    return out


#: pandas resample rule + Period alias per non-daily frequency.
_RESAMPLE_RULE: dict[str, tuple[str, str]] = {
    "weekly": ("W", "W"),
    "monthly": ("ME", "M"),
}


def _partial_sum(s: pd.Series) -> float:
    """Sum that stays NaN when every input is missing (unlike ``Series.sum()``)."""
    return float(s.sum(min_count=1))


def resample_bars(df: pd.DataFrame, freq: str = "daily") -> pd.DataFrame:
    """Aggregate daily bars into weekly (W) or monthly (ME) bars.

    Weekly bars are stamped with the **last** trading date in the bucket, not the
    calendar week's Friday: A-share weeks are trading weeks, and aligning the label to
    the real last session keeps the chart's x-axis matching the other pages' 截至日.
    Volume/amount sum; open is the first, close the last, high/low the extremes.
    """
    key = (freq or "daily").strip().lower()
    if df is None or df.empty or "date" not in df.columns or key not in _RESAMPLE_RULE:
        return df
    rule, per = _RESAMPLE_RULE[key]
    d = df.copy()
    d["_ts"] = pd.to_datetime(d["date"], errors="coerce")
    d = d[d["_ts"].notna()].sort_values("_ts")
    if d.empty:
        return df
    d = d.set_index("_ts")
    agg: dict[str, Callable[[pd.Series], Any]] = {}
    # ``min_count=1`` on the sums matters: a feed that never populates a column stores
    # all-NULL, and pandas' default ``sum()`` turns an all-missing bucket into ``0.0``.
    # That invents a real zero where the truth is "unknown" — and a zero 成交额 reads as
    # the thinnest possible book, which is how resampled index bars ended up excluded
    # from the signal matrix as 低流动.
    for col, how in (("open", "first"), ("high", "max"), ("low", "min"),
                     ("close", "last"), ("pre_close", "last"),
                     ("turnover_rate", "mean"), ("change_pct", "last")):
        if col in d.columns:
            agg[col] = how
    for col in ("volume", "amount", "oi"):
        if col in d.columns:
            agg[col] = _partial_sum
    if not agg:
        return df
    out = d.resample(rule).agg(agg).dropna(subset=["close"])
    if out.empty:
        return df
    # Stamp each bar with the last real session date inside its bucket.
    last_date = pd.Series(d.index, index=d.index.to_period(per)).groupby(level=0).max()
    out["date"] = pd.Index(out.index.to_period(per).map(last_date)).strftime("%Y-%m-%d")
    cols = [c for c in ("date", *agg.keys()) if c in out.columns]
    return out[cols].reset_index(drop=True)


def _nan_to_none(x: float) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except (TypeError, ValueError):
        return None


def build_series(df: pd.DataFrame, names: list[str] | None = None,
                 bars: int = 250, code: str = "", freq: str = "daily",
                 params: dict[str, dict] | None = None) -> dict:
    """Build an ECharts-ready payload. Indicators are computed over the FULL frame
    (so leading values warm up), then every series is trimmed to the last ``bars``.

    ``bars`` counts *output* bars in the requested ``freq``; for weekly/monthly the
    caller must therefore load ~5x/~21x the daily rows (see ``FREQ_BARS``).
    """
    empty = {"code": code, "freq": freq, "dates": [], "candle": [], "volume": [], "indicators": {}}
    if df is None or df.empty:
        return empty
    key = (freq or "daily").strip().lower()
    d_full = resample_bars(df, key) if key in _RESAMPLE_RULE else df
    ind_full = compute(d_full, names, params)
    d = d_full.tail(bars).copy() if bars else d_full.copy()
    o, high, low, c = _col(d, "open"), _col(d, "high"), _col(d, "low"), _col(d, "close")
    v = _col(d, "volume") if "volume" in d.columns else pd.Series(0.0, index=d.index)
    dates = [str(x) for x in d["date"].tolist()] if "date" in d.columns else [str(i) for i in d.index]
    # strict=True: all four columns come from the same frame, so a length mismatch would
    # mean a malformed frame — silently truncating via zip would emit a candle chart whose
    # open/close and low/high belong to different bars.
    candle = [[_nan_to_none(a), _nan_to_none(b), _nan_to_none(cc), _nan_to_none(dd)]
              for a, b, cc, dd in zip(o, c, low, high, strict=True)]
    volume = [_nan_to_none(x) for x in v]
    ind_payload: dict[str, dict[str, list]] = {}
    for name, frame in ind_full.items():
        tail = frame.tail(bars) if bars else frame
        ind_payload[name] = {col: [_nan_to_none(x) for x in tail[col]] for col in tail.columns}
    return {"code": code, "freq": key, "dates": dates, "candle": candle,
            "volume": volume, "indicators": ind_payload}
