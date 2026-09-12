"""Technical indicator engine — pure numpy/pandas (NO TA-Lib / pandas-ta).

Rationale (per plan): TA-Lib has painful native builds on Windows and pandas-ta has
maintenance risk, so indicators are implemented directly. Formulas follow the common
通达信/同花顺 definitions so values match what CN users expect.

Input DataFrame columns (case-insensitive, at least): open, high, low, close, volume.
Optional: amount, turnover_rate, oi.

Public API:
    compute(df, names) -> dict[str, pd.DataFrame]
    build_series(df, names, bars, code) -> ECharts-ready dict
    INDICATORS / ALIASES registries
"""
from __future__ import annotations

import math
from typing import Callable

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


# ----------------------------- indicators -----------------------------

def ind_ma(df: pd.DataFrame) -> pd.DataFrame:
    c = _col(df, "close")
    return pd.DataFrame({f"ma{n}": _ma(c, n) for n in (5, 10, 20, 60)}, index=df.index)


def ind_ema(df: pd.DataFrame) -> pd.DataFrame:
    c = _col(df, "close")
    return pd.DataFrame({f"ema{n}": _ema(c, n) for n in (12, 26, 50)}, index=df.index)


def ind_boll(df: pd.DataFrame, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    c = _col(df, "close")
    mid = _ma(c, n)
    sd = c.rolling(n, min_periods=1).std(ddof=0)
    return pd.DataFrame({"boll_mid": mid, "boll_up": mid + k * sd, "boll_low": mid - k * sd}, index=df.index)


def ind_boll_ext(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    c = _col(df, "close")
    mid = _ma(c, n)
    sd = c.rolling(n, min_periods=1).std(ddof=0)
    pctb = (c - (mid - 2 * sd)) / (4 * sd).replace(0, np.nan)
    bandwidth = (4 * sd) / mid.replace(0, np.nan)
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


def ind_rsi(df: pd.DataFrame) -> pd.DataFrame:
    c = _col(df, "close")
    diff = c.diff()
    up = diff.clip(lower=0)
    ad = diff.abs()
    out = {}
    for n in (6, 12, 24):
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
    adx = _sma_cn((mdi - pdi).abs() / (mdi + pdi).replace(0, np.nan) * 100, m, 1)
    adxr = (adx + adx.shift(m)) / 2
    return pd.DataFrame({"dmi_pdi": pdi, "dmi_mdi": mdi, "dmi_adx": adx, "dmi_adxr": adxr}, index=df.index)


def ind_atr(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    return pd.DataFrame({"atr": _sma_cn(_tr(df), n, 1)}, index=df.index)


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
    return pd.DataFrame({"kelt_mid": mid, "kelt_up": mid + k * atr, "kelt_low": mid - k * atr}, index=df.index)


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


def ind_bias(df: pd.DataFrame) -> pd.DataFrame:
    c = _col(df, "close")
    out = {}
    for n in (6, 12, 24):
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
    return pd.DataFrame({"asi": si.fillna(0).cumsum(), "asit": _ma(si.fillna(0).cumsum(), 10)}, index=df.index)


def ind_hv(df: pd.DataFrame, n: int = 24) -> pd.DataFrame:
    c = _col(df, "close")
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


INDICATORS: dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
    "ma": ind_ma, "ema": ind_ema, "boll": ind_boll, "boll_ext": ind_boll_ext,
    "macd": ind_macd, "kdj": ind_kdj, "rsi": ind_rsi, "dmi": ind_dmi, "atr": ind_atr,
    "obv": ind_obv, "sar": ind_sar, "cci": ind_cci, "wr": ind_wr, "bbi": ind_bbi,
    "donchian": ind_donchian, "keltner": ind_keltner, "trix": ind_trix, "aroon": ind_aroon,
    "mavol": ind_mavol, "skdj": ind_skdj, "roc": ind_roc, "mtm": ind_mtm, "bias": ind_bias,
    "psy": ind_psy, "cr": ind_cr, "vr": ind_vr, "mfi": ind_mfi, "emv": ind_emv,
    "qrr": ind_qrr, "asi": ind_asi, "hv": ind_hv, "oi": ind_oi, "turnover": ind_turnover,
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
}

DEFAULT_INDICATORS = ["ma", "macd", "kdj", "rsi", "boll", "mavol"]


def _resolve(name: str) -> str:
    n = name.strip().lower()
    return ALIASES.get(n, ALIASES.get(name.strip(), n))


def compute(df: pd.DataFrame, names: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """Compute requested indicators over an OHLCV frame. Unknown names are skipped."""
    names = names or DEFAULT_INDICATORS
    out: dict[str, pd.DataFrame] = {}
    for raw in names:
        key = _resolve(raw)
        fn = INDICATORS.get(key)
        if fn is None:
            continue
        try:
            res = fn(df)
            if isinstance(res, pd.DataFrame) and not res.empty:
                out[key] = res
        except Exception:  # noqa: BLE001
            continue
    return out


def _nan_to_none(x: float) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    except (TypeError, ValueError):
        return None


def build_series(df: pd.DataFrame, names: list[str] | None = None,
                 bars: int = 250, code: str = "") -> dict:
    """Build an ECharts-ready payload. Indicators are computed over the FULL frame
    (so leading values warm up), then every series is trimmed to the last ``bars``."""
    if df is None or df.empty:
        return {"code": code, "dates": [], "candle": [], "volume": [], "indicators": {}}
    ind_full = compute(df, names)
    d = df.tail(bars).copy() if bars else df.copy()
    o, h, l, c = _col(d, "open"), _col(d, "high"), _col(d, "low"), _col(d, "close")
    v = _col(d, "volume") if "volume" in d.columns else pd.Series(0.0, index=d.index)
    dates = [str(x) for x in d["date"].tolist()] if "date" in d.columns else [str(i) for i in d.index]
    candle = [[_nan_to_none(a), _nan_to_none(b), _nan_to_none(cc), _nan_to_none(dd)]
              for a, b, cc, dd in zip(o, c, l, h)]
    volume = [_nan_to_none(x) for x in v]
    ind_payload: dict[str, dict[str, list]] = {}
    for name, frame in ind_full.items():
        tail = frame.tail(bars) if bars else frame
        ind_payload[name] = {col: [_nan_to_none(x) for x in tail[col]] for col in tail.columns}
    return {"code": code, "dates": dates, "candle": candle, "volume": volume, "indicators": ind_payload}
