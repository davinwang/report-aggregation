"""Indicator engine tests — verify formulas against hand-computed values."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.indicators import (
    ALIASES,
    INDICATORS,
    build_series,
    compute,
    ind_ma,
    ind_rsi,
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
