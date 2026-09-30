"""技术指标 (quant) endpoints — K-line series, indicator catalog, and signal matrix.

``/api/quant/series`` provides server-computed indicators; indicators are computed in
Python (``services.indicators``) over stored bars and returned ECharts-ready.

``/api/quant/signal-matrix`` is the 品种 × 指标 direction table: every column is one
rule that turns an indicator reading into 偏多/偏空/中性/弃权, and the row's ``net`` is the
signed tally of the columns that actually voted. Computation lives in
``services.signal_matrix`` so the MCP tool shares one implementation and one cache.
"""
from __future__ import annotations

import inspect
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.db import get_db
from app.services import matrix as matrix_svc
from app.services import signal_matrix as signal_svc
from app.services.indicators import (
    DEFAULT_INDICATORS,
    FREQ_BARS,
    FREQS,
    INDICATORS,
    _resolve,
    build_series,
    catalog,
)
from app.services.quotes import load_bars

router = APIRouter(prefix="/api/quant", tags=["quant"])

WARMUP = 80  # extra bars loaded before the requested window for indicator warmup

# Period string → approximate trading days.
_PERIOD_MAP: dict[str, int] = {
    "6m": 120,
    "1y": 250,
    "2y": 500,
    "3y": 750,
    "5y": 1250,
}


def _resolve_bars(period: str) -> int:
    """Convert a human-friendly period like '6m'/'1y' to trading-day count."""
    if period in _PERIOD_MAP:
        return _PERIOD_MAP[period]
    # Fallback: try interpreting as a plain integer (legacy `bars` value).
    try:
        return max(10, min(int(period), 1500))
    except (ValueError, TypeError):
        return 250


def _resolve_freq(freq: str | None) -> str:
    f = (freq or "daily").strip().lower()
    return f if f in FREQS else "daily"


def _parse_params(raw: str | None) -> dict[str, dict]:
    """Decode the ``params`` query into ``{indicator: {kwarg: value}}``.

    Two accepted forms:

    - JSON: ``{"ma": {"periods": [5, 10]}, "macd": {"fast": 5, "slow": 35}}`` — can set
      any keyword the indicator accepts.
    - Compact ``indicator=value[;...]``: ``ma=5,10,20;boll=10``. This can only carry one
      primary period, so the keyword is resolved against the target function's signature
      (``n`` for 布林/唐奇安, ``periods`` for 均线/RSI…) instead of being guessed.

    Malformed input is ignored rather than 400-ing: a typo in one indicator's parameters
    should degrade that indicator, not break the chart.
    """
    if not raw:
        return {}
    text = raw.strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return {}
        return {k: v for k, v in parsed.items() if isinstance(v, dict)} if isinstance(parsed, dict) else {}
    out: dict[str, dict] = {}
    for chunk in text.split(";"):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        kwargs = _compact_kwargs(key.strip(), value.strip())
        if kwargs:
            out[key.strip()] = kwargs
    return out


#: Preference order for the compact form's single keyword, most specific first.
_PRIMARY_KWARG = ("n", "periods", "fast", "step", "k")


def _compact_kwargs(key: str, value: str) -> dict:
    """Map ``ma=5,10`` onto the right keyword of that indicator's implementation."""
    if not key or not value:
        return {}
    fn = INDICATORS.get(_resolve(key))
    if fn is None:
        return {}
    try:
        accepted = set(inspect.signature(fn).parameters) - {"df"}
    except (TypeError, ValueError):  # pragma: no cover - all indicators are plain functions
        return {}
    for candidate in _PRIMARY_KWARG:
        if candidate in accepted:
            if "," in value:
                return {candidate: [p.strip() for p in value.split(",") if p.strip()]}
            for cast in (int, float, str):
                try:
                    return {candidate: cast(value)}
                except ValueError:
                    continue
    return {}


@router.get("/series")
def series(
    code: str = Query(..., description="security code, e.g. 600519 / sh000300 / 510300 / 113050"),
    freq: str = Query(default="daily", description="daily|weekly|monthly"),
    indicators: str | None = Query(default=None, description="comma-separated, e.g. ma,macd,kdj"),
    period: str = Query(default="1y", description="lookback period: 6m|1y|2y|3y|5y"),
    adjust: str | None = Query(default=None, description="qfq|hfq|raw|none"),
    params: str | None = Query(default=None, description='indicator overrides, e.g. "ma=5,10,20" or JSON'),
    db: Session = Depends(get_db),
) -> dict:
    names = [x for x in (indicators or "").split(",") if x] or DEFAULT_INDICATORS
    bars = _resolve_bars(period)
    key = _resolve_freq(freq)
    # ``bars`` counts output bars, so a weekly/monthly chart needs that many *daily*
    # rows multiplied up before resampling (5 sessions a week, ~21 a month).
    df = load_bars(db, code, limit=bars * FREQ_BARS[key] + WARMUP, prefer_adjust=adjust)
    payload = build_series(df, names=names, bars=bars, code=code, freq=key,
                           params=_parse_params(params))
    return envelope(payload, freq=key, indicators=names, count=len(payload["dates"]),
                    period=period)


@router.get("/indicator-catalog")
def indicator_catalog(
    group: str | None = Query(default=None, description="filter by 趋势|震荡|动量|量价|波动|衍生品"),
) -> dict:
    """Every supported indicator with its Chinese label, pane, formula and parameters.

    Drives the chart's indicator picker and the 指标说明 panel, so the UI never hard-codes
    an indicator list that can drift from the engine.
    """
    items = catalog([group] if group else None)
    return envelope(items, groups=sorted({i["group"] for i in items}), count=len(items))


@router.get("/signal-matrix")
def signal_matrix(
    scope: str = Query(default="index", description="index|index+all|etf|bond|stock|all"),
    columns: str | None = Query(default=None, description="comma-separated rule keys"),
    freq: str = Query(default="daily", description="daily|weekly|monthly"),
    limit: int = Query(default=60, ge=1, le=500),
    liquidity_floor: float = Query(default=signal_svc.LIQUIDITY_FLOOR, ge=0,
                                   description="日均成交额下限(元); 低于此值不参与表决"),
    db: Session = Depends(get_db),
) -> dict:
    """技术信号矩阵: 每列一个指标的 偏多/偏空/中性/弃权 表决 + 净方向排序.

    Rows whose data is stale or below ``liquidity_floor`` are still returned (their
    readings are real) but are excluded from the market tally, with the reason on the row.
    """
    payload = signal_svc.snapshot(
        db,
        scope=scope,
        columns=[x.strip() for x in (columns or "").split(",") if x.strip()] or None,
        freq=_resolve_freq(freq),
        limit=limit,
        liquidity_floor=liquidity_floor,
    )
    return envelope(payload, count=len(payload["rows"]), scope=scope)


@router.get("/signal-rules")
def signal_rules() -> dict:
    """The direction rules behind each matrix column, for the 口径说明 panel."""
    return envelope(signal_svc.rules_catalog(), count=len(signal_svc.DEFAULT_RULES),
                    states=signal_svc.STATE_LABELS, scopes=list(signal_svc.SCOPES))


@router.get("/matrix")
def matrix(
    freq: str = Query(default="daily"),
    limit: int = Query(default=60, ge=1, le=300),
    scope: str = Query(default="index+active", description="index|index+active"),
    db: Session = Depends(get_db),
) -> dict:
    """Technical snapshot matrix across a bounded set of securities (全市场速览).

    Computation + caching live in ``services.matrix`` so the MCP tool shares the
    same ready payload (same cache key); this route stays thin.
    """
    rows = matrix_svc.snapshot(db, scope=scope, limit=limit)
    return envelope(rows, freq=freq, count=len(rows))
