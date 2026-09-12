"""Normalizer unit tests — the first line of defense against messy source data."""
from __future__ import annotations

from datetime import date

from app.ingestion.normalizers import (
    clean_text,
    em_symbol,
    norm_code,
    norm_rating,
    rating_change_kind,
    sina_symbol,
    to_date,
    to_float,
    to_int,
    to_period_str,
)
from app.models.base import RatingDirection


def test_to_float_units_and_percent():
    assert to_float("1.5万") == 15000
    assert to_float("2亿") == 200000000
    assert to_float("12.3%") == 12.3
    assert to_float("1,234.5") == 1234.5
    assert to_float(3) == 3.0
    assert to_float("--") is None
    assert to_float("暂无") is None
    assert to_float("", default=0.0) == 0.0


def test_to_int():
    assert to_int("12.6") == 13
    assert to_int("暂无") is None


def test_to_date_formats():
    assert to_date("2024-01-02") == date(2024, 1, 2)
    assert to_date("20240102") == date(2024, 1, 2)
    assert to_date("2024/1/2") == date(2024, 1, 2)
    assert to_date("2024-01-02 15:00:00") == date(2024, 1, 2)
    assert to_date("bad") is None


def test_to_period_str():
    assert to_period_str("2024-03-31") == "20240331"
    assert to_period_str("20240331") == "20240331"


def test_code_normalization():
    assert norm_code("SH600519") == "600519"
    assert norm_code("600519.SH") == "600519"
    assert norm_code("sz000001") == "000001"
    assert em_symbol("600519") == "SH600519"
    assert em_symbol("000001") == "SZ000001"
    assert sina_symbol("600519") == "sh600519"


def test_clean_text():
    assert clean_text("  a   b ") == "a b"
    assert clean_text("--") is None


def test_norm_rating_maps_sources():
    assert norm_rating("买入") == RatingDirection.buy
    assert norm_rating("强烈推荐") == RatingDirection.buy
    assert norm_rating("增持") == RatingDirection.overweight
    assert norm_rating("持有") == RatingDirection.neutral
    assert norm_rating("减持") == RatingDirection.underweight
    assert norm_rating("卖出") == RatingDirection.sell
    assert norm_rating("不评级") == RatingDirection.unknown
    assert norm_rating(None) == RatingDirection.unknown


def test_rating_change_kind():
    assert rating_change_kind("中性", "买入") == "上调"
    assert rating_change_kind("买入", "增持") == "下调"
    assert rating_change_kind("买入", "买入") == "维持"
    assert rating_change_kind(None, "增持") == "首次"
