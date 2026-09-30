"""Indicator engine tests — verify formulas against hand-computed values."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.indicators import (
    ALIASES,
    INDICATOR_META,
    INDICATORS,
    build_series,
    catalog,
    compute,
    ind_atr,
    ind_ma,
    ind_rsi,
    resample_bars,
)


def _frame(n: int = 60) -> pd.DataFrame:
    close = pd.Series(np.linspace(10, 40, n))
    open_ = close.shift(1).fillna(close.iloc[0])
    # valid OHLC: high/low must envelop both open and close
    high = pd.concat([open_, close], axis=1).max(axis=1) + 0.5
    low = pd.concat([open_, close], axis=1).min(axis=1) - 0.5
    vol = pd.Series(np.linspace(1e6, 2e6, n))
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n).strftime("%Y-%m-%d"),
        "open": open_, "high": high, "low": low, "close": close, "volume": vol,
    })


def test_ma_known_value():
    df = pd.DataFrame({
        "open": [1.0] * 10, "high": [1.0] * 10, "low": [1.0] * 10,
        "close": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "volume": [1] * 10,
    })
    ma = ind_ma(df)
    assert abs(ma["ma5"].iloc[-1] - 8.0) < 1e-9   # mean(6..10)
    assert abs(ma["ma10"].iloc[-1] - 5.5) < 1e-9  # mean(1..10)


def test_rsi_bounds():
    rsi = ind_rsi(_frame())
    vals = rsi["rsi6"].dropna()
    assert ((vals >= 0) & (vals <= 100)).all()


def test_compute_returns_requested_and_skips_unknown():
    df = _frame()
    out = compute(df, ["ma", "macd", "kdj", "boll", "not_a_real_indicator"])
    assert "ma" in out and "macd" in out and "kdj" in out and "boll" in out
    assert "not_a_real_indicator" not in out
    assert {"macd_dif", "macd_dea", "macd"}.issubset(out["macd"].columns)


def test_all_indicators_run_without_error():
    df = _frame(120)
    for name, fn in INDICATORS.items():
        res = fn(df)
        assert isinstance(res, pd.DataFrame), name


def test_aliases_resolve():
    assert ALIASES["布林"] == "boll"
    assert ALIASES["持仓量"] == "oi"
    assert ALIASES["换手率"] == "turnover"


def test_build_series_shape_and_candle_order():
    df = _frame(60)
    payload = build_series(df, names=["ma", "macd"], bars=30, code="600519")
    assert payload["code"] == "600519"
    assert len(payload["dates"]) == 30
    assert len(payload["candle"]) == 30
    # candle row is [open, close, low, high]
    first = payload["candle"][0]
    assert len(first) == 4
    o, c, low, high = first
    assert low <= min(o, c) and high >= max(o, c)
    assert "ma" in payload["indicators"] and "macd" in payload["indicators"]
    assert len(payload["indicators"]["ma"]["ma5"]) == 30


def test_build_series_empty():
    payload = build_series(pd.DataFrame(), names=["ma"], bars=10, code="x")
    assert payload["dates"] == [] and payload["candle"] == []


# ---- registry / catalog integrity ----

def test_every_indicator_is_catalogued_and_backed():
    """The UI renders the indicator list from the catalog, so the two must not drift."""
    assert set(INDICATORS) == set(INDICATOR_META), (
        sorted(set(INDICATORS) ^ set(INDICATOR_META)))
    items = catalog()
    assert len(items) == len(INDICATORS)
    for item in items:
        assert item["label"] and item["desc"] and item["group"]
        assert item["pane"] in ("main", "sub")
        assert item["columns"], item["key"]


def test_catalog_aliases_resolve_back_to_their_key():
    for item in catalog():
        for alias in item["aliases"]:
            assert ALIASES[alias] == item["key"]


def test_catalog_group_filter():
    labels = [i["group"] for i in catalog(["趋势"])]
    assert labels and set(labels) == {"趋势"}


# ---- parameter overrides ----

def test_period_overrides_change_the_columns():
    df = _frame(120)
    assert list(ind_ma(df, periods=[3, 8]).columns) == ["ma3", "ma8"]
    assert list(ind_ma(df, periods="3,8").columns) == ["ma3", "ma8"]
    assert list(ind_ma(df, periods=7).columns) == ["ma7"]
    assert list(ind_rsi(df, periods=14).columns) == ["rsi14"]


def test_bad_period_override_falls_back_to_the_default():
    """A typo must not silently produce an indicator with no columns."""
    assert list(ind_ma(_frame(40), periods=["x", ""]).columns) == ["ma5", "ma10", "ma20", "ma60"]
    assert list(ind_ma(_frame(40), periods=[]).columns) == ["ma5", "ma10", "ma20", "ma60"]


def test_compute_applies_params_and_isolates_bad_ones():
    df = _frame(120)
    out = compute(df, ["ma", "rsi", "kdj"],
                  {"ma": {"periods": [3, 8]}, "rsi": {"nope": 1}, "kdj": {"n": "x"}})
    assert list(out["ma"].columns) == ["ma3", "ma8"]
    # A rejected keyword drops only that indicator; the rest of the payload survives.
    assert "rsi" not in out and "kdj" not in out


def test_atr_pct_is_price_relative():
    """atr_pct must be comparable across instruments; atr alone is not."""
    df = _frame(120)
    out = ind_atr(df)
    assert {"atr", "atr_pct"}.issubset(out.columns)
    ratio = (out["atr_pct"] / out["atr"]).dropna()
    assert (ratio > 0).all()


# ---- volume-price additions ----

def test_vwap_tracks_a_constant_price():
    """With a flat close the VWAP *is* that price, and the deviation is zero."""
    n = 60
    df = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n).strftime("%Y-%m-%d"),
        "open": [5.0] * n, "high": [5.0] * n, "low": [5.0] * n, "close": [5.0] * n,
        "volume": [1000.0] * n, "amount": [5000.0] * n,
    })
    out = compute(df, ["vwap"])["vwap"]
    assert abs(out["vwap"].iloc[-1] - 5.0) < 1e-9
    assert abs(out["vwap_dev"].iloc[-1]) < 1e-9


def test_vwap_survives_feeds_without_amount():
    """可转债/index bars carry no 成交额 — the indicator must degrade, not vanish."""
    df = _frame(120).drop(columns=["amount"], errors="ignore")
    out = compute(df, ["vwap"])["vwap"]
    assert out["vwap"].notna().any()


def test_ma_align_is_bounded():
    align = compute(_frame(120), ["ma_align"])["ma_align"]["ma_align"]
    assert ((align >= 0) & (align <= 100)).all()


def test_brar_saturates_on_one_sided_windows():
    """A pure uptrend has no bars on the losing side; BR must read 强烈偏多, not NaN."""
    out = compute(_frame(120), ["brar"])["brar"]
    assert out["brar_br"].dropna().gt(0).all()
    assert out["brar_ar"].dropna().gt(0).all()
    assert out["brar_br"].iloc[-1] >= 100

    # BR routinely exceeds 100 (that's its normal range) and can legitimately hit 0 when a
    # window contains no bars above the average price — but it must stay finite, never NaN
    # and never negative.
    both = compute(_trading_days(120), ["brar"])["brar"]["brar_br"].dropna()
    assert len(both) > 100
    assert (both >= 0).all() and np.isfinite(both).all()
    assert both.max() > 100


def test_brar_is_all_nan_on_a_flat_series():
    """No bars on either side is genuinely undefined — must not invent a value."""
    n = 60
    flat = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n).strftime("%Y-%m-%d"),
        "open": [5.0] * n, "high": [5.0] * n, "low": [5.0] * n, "close": [5.0] * n,
        "volume": [1000.0] * n,
    })
    out = compute(flat, ["brar"])["brar"]
    assert out["brar_br"].isna().all()


def test_indicators_degrade_when_a_needed_column_is_missing():
    """Index bars have no 换手率/持仓量; those columns drop out, the rest still compute."""
    df = _frame(120).drop(columns=["turnover_rate", "amount"], errors="ignore")
    out = compute(df, sorted(INDICATORS))
    assert "turnover" not in out
    assert "oi" not in out
    assert {"ma", "macd", "vwap"}.issubset(out)


# ---- resampling ----

def _trading_days(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)))
    open_ = close.shift(1).fillna(100.0)
    high = pd.concat([open_, close], axis=1).max(axis=1) + 0.5
    low = pd.concat([open_, close], axis=1).min(axis=1) - 0.5
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n, freq="B").strftime("%Y-%m-%d"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.uniform(1e6, 2e6, n), "amount": rng.uniform(1e8, 2e8, n),
    })


def test_resample_weekly_stamps_the_last_session_of_each_bucket():
    df = _trading_days(60)
    out = resample_bars(df, "weekly")
    assert 0 < len(out) < len(df)
    # Every bar's label must be a date that actually exists in the daily frame.
    assert set(out["date"]).issubset(set(df["date"]))
    # ...and it must be the last session of its own bucket.
    first_week = df[df["date"] <= out["date"].iloc[0]]["date"].max()
    assert out["date"].iloc[0] == first_week


def test_resample_conserves_volume_and_keeps_ohlc_consistent():
    df = _trading_days(60)
    for freq in ("weekly", "monthly"):
        out = resample_bars(df, freq)
        assert abs(out["volume"].sum() - df["volume"].sum()) < 1e-6
        assert (out["high"] >= out["low"]).all()
        assert (out["high"] >= out["close"]).all()
        assert (out["low"] <= out["close"]).all()
        assert (out["high"] >= out["open"]).all()
        assert (out["low"] <= out["open"]).all()


def test_resample_daily_is_a_no_op():
    df = _trading_days(30)
    assert len(resample_bars(df, "daily")) == len(df)


def test_resample_ignores_unusable_frames():
    assert resample_bars(pd.DataFrame(), "weekly").empty
    no_date = _trading_days(10).drop(columns=["date"])
    assert len(resample_bars(no_date, "weekly")) == 10


def test_build_series_honours_freq():
    df = _trading_days(260)
    daily = build_series(df, ["ma"], bars=40, code="x", freq="daily")
    weekly = build_series(df, ["ma"], bars=40, code="x", freq="weekly")
    assert weekly["freq"] == "weekly"
    assert len(weekly["dates"]) < len(daily["dates"]) or len(weekly["dates"]) == 40
    # Indicators must be computed on the resampled bars, not the daily ones.
    assert len(weekly["indicators"]["ma"]["ma5"]) == len(weekly["dates"])


def test_build_series_echoes_freq_even_when_empty():
    assert build_series(pd.DataFrame(), freq="monthly")["freq"] == "monthly"
