"""Normalizers for messy public-source data.

AkShare returns DataFrames scraped from 东财/新浪/巨潮 with inconsistent types:
numbers as strings with 万/亿/%/, suffixes, '--'/'None'/'' for missing, dates in
multiple formats, and rating vocabularies that differ per source. Everything passes
through here so downstream code sees clean Python types.
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from app.models.base import RatingDirection

_MISSING = {"", "-", "--", "—", "none", "null", "nan", "n/a", "暂无", "不适用"}

_CN_NUM = {"万": 1e4, "亿": 1e8, "千": 1e3, "w": 1e4, "W": 1e4}

# Map assorted rating vocabularies -> normalized direction.
_RATING_MAP: dict[str, RatingDirection] = {
    "买入": RatingDirection.buy, "强烈推荐": RatingDirection.buy, "推荐": RatingDirection.buy,
    "强推": RatingDirection.buy, "优于大市": RatingDirection.buy, "跑赢行业": RatingDirection.buy,
    "谨慎推荐": RatingDirection.buy, "审慎推荐": RatingDirection.buy, "buy": RatingDirection.buy,
    "增持": RatingDirection.overweight, "增持评级": RatingDirection.overweight,
    "谨慎增持": RatingDirection.overweight,
    "outperform": RatingDirection.overweight, "增持(上一评级": RatingDirection.overweight,
    "中性": RatingDirection.neutral, "持有": RatingDirection.neutral, "观望": RatingDirection.neutral,
    "同步大市": RatingDirection.neutral, "标配": RatingDirection.neutral, "neutral": RatingDirection.neutral,
    "hold": RatingDirection.neutral, "中性和尚": RatingDirection.neutral,
    "减持": RatingDirection.underweight, "减持评级": RatingDirection.underweight,
    "underperform": RatingDirection.underweight, "弱于大市": RatingDirection.underweight,
    "卖出": RatingDirection.sell, "回避": RatingDirection.sell, "sell": RatingDirection.sell,
    "不评级": RatingDirection.unknown, "无": RatingDirection.unknown, "未评级": RatingDirection.unknown,
}


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip().lower() in _MISSING:
        return True
    return False


def to_float(v: Any, default: float | None = None) -> float | None:
    """Parse a numeric value that may carry 万/亿/%/, suffixes or be missing."""
    if _is_missing(v):
        return default
    if isinstance(v, (int, float)):
        f = float(v)
        return default if math.isnan(f) else f
    s = str(v).strip().replace(",", "").replace("，", "")
    pct = s.endswith("%")
    if pct:
        s = s[:-1]
    mult = 1.0
    for suf, m in _CN_NUM.items():
        if s.endswith(suf):
            s = s[: -len(suf)]
            mult = m
            break
    try:
        f = float(s) * mult
        if pct:
            f = f  # keep percentage as-is (e.g. 12.3 means 12.3%)
        return default if math.isnan(f) else f
    except (ValueError, TypeError):
        return default


def to_int(v: Any, default: int | None = None) -> int | None:
    f = to_float(v, None)
    if f is None:
        return default
    try:
        return int(round(f))
    except (ValueError, OverflowError):
        return default


def to_date(v: Any) -> date | None:
    """Parse dates from str/date/datetime in common CN formats (2024-01-01, 20240101, 2024/1/1)."""
    if _is_missing(v):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    s = s.split(" ")[0].split("T")[0]
    s = s.replace("/", "-").replace(".", "-").replace("年", "-").replace("月", "-").replace("日", "")
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m", "%m-%d"):
        try:
            d = datetime.strptime(s, fmt)
            return d.date()
        except ValueError:
            continue
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def to_period_str(v: Any) -> str | None:
    """Normalize a report period to YYYYMMDD string (e.g. 20240331)."""
    d = to_date(v)
    if d is not None:
        return d.strftime("%Y%m%d")
    s = str(v).strip().replace("-", "").replace("/", "")
    return s[:8] if re.match(r"^\d{8}", s) else None


def clean_text(v: Any, default: str | None = None) -> str | None:
    if _is_missing(v):
        return default
    return re.sub(r"\s+", " ", str(v)).strip()


def norm_code(v: Any) -> str | None:
    """Normalize a security code to a bare digit string (6-digit A-share) when possible."""
    s = clean_text(v, "")
    if not s:
        return None
    s = s.upper()
    # strip exchange prefixes/suffixes: SH600000 / 600000.SH / sh600000
    s = re.sub(r"^(SH|SZ|BJ)", "", s)
    s = re.sub(r"\.(SH|SZ|BJ)$", "", s)
    return s


def exchange_of(code: str) -> str:
    """Guess exchange from an A-share code."""
    c = norm_code(code) or ""
    if c.startswith(("60", "68", "9", "5")):
        return "SSE"
    if c.startswith(("00", "30", "2", "1")):
        return "SZSE"
    if c.startswith(("43", "83", "87", "92", "4")):
        return "BSE"
    return ""


def em_symbol(code: str) -> str:
    """东财财务接口格式: SH600519 / SZ000001."""
    c = norm_code(code) or ""
    ex = exchange_of(c)
    prefix = {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(ex, "SH")
    return f"{prefix}{c}"


def sina_symbol(code: str) -> str:
    """新浪格式: sh600000 / sz000001."""
    return em_symbol(code).lower()


def norm_rating(v: Any) -> RatingDirection:
    """Map any source rating string to a normalized RatingDirection."""
    s = clean_text(v, "")
    if not s:
        return RatingDirection.unknown
    if s in _RATING_MAP:
        return _RATING_MAP[s]
    # substring fallback (e.g. "增持(上一评级)")
    for key, direction in _RATING_MAP.items():
        if key and key in s:
            return direction
    return RatingDirection.unknown


# Ordered strength of ratings, used by accuracy/signals services.
RATING_SCORE: dict[RatingDirection, int] = {
    RatingDirection.buy: 2,
    RatingDirection.overweight: 1,
    RatingDirection.neutral: 0,
    RatingDirection.underweight: -1,
    RatingDirection.sell: -2,
    RatingDirection.unknown: 0,
}


def rating_change_kind(prev: Any, cur: Any) -> str:
    """Return 上调/下调/维持/首次 based on normalized rating movement."""
    p, c = norm_rating(prev), norm_rating(cur)
    if p == RatingDirection.unknown and c != RatingDirection.unknown:
        return "首次"
    if c == RatingDirection.unknown:
        return "未知"
    if RATING_SCORE[c] > RATING_SCORE[p]:
        return "上调"
    if RATING_SCORE[c] < RATING_SCORE[p]:
        return "下调"
    return "维持"
