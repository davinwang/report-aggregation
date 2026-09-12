"""Financial statement data (财报) — a NEW module for the stock version.

Wide statement rows (300+ fields from 东财) are stored as JSON keyed by report period;
a curated ``FinancialIndicator`` table backs fast listing/sorting; ``Disclosure`` stores
公告原文 links from 巨潮/东财.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import JSON, Date, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FinancialStatement(Base, TimestampMixin):
    """One statement (balance/income/cashflow) for a security at a report period.

    ``data_json`` holds the raw field map from the source (em or sina). Source is part of
    the unique key so em & sina copies can coexist for cross-checking/fallback.
    """

    __tablename__ = "financial_statement"
    __table_args__ = (
        UniqueConstraint("code", "report_period", "statement", "source", name="uq_finstmt"),
        Index("ix_finstmt_code", "code"),
        Index("ix_finstmt_period", "report_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(16))
    report_period: Mapped[str] = mapped_column(String(16))    # e.g. "20240331"
    statement: Mapped[str] = mapped_column(String(16))        # balance|income|cashflow
    source: Mapped[str] = mapped_column(String(16), default="em")   # em|sina
    data_json: Mapped[dict] = mapped_column(JSON, default=dict)


class FinancialIndicator(Base, TimestampMixin):
    """Curated key metrics (``stock_financial_analysis_indicator``) for fast display/sort."""

    __tablename__ = "financial_indicator"
    __table_args__ = (
        UniqueConstraint("code", "report_period", name="uq_finind_code_period"),
        Index("ix_finind_code", "code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(16))
    report_period: Mapped[str] = mapped_column(String(16))
    eps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)             # 每股收益
    bps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)             # 每股净资产
    roe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)             # 净资产收益率
    roa: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)         # 营业收入
    revenue_yoy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)      # 净利润
    net_profit_yoy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # 毛利率
    net_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)      # 净利率
    debt_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)      # 资产负债率
    ocfps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)           # 每股经营现金流
    extra_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class EarningsReport(Base, TimestampMixin):
    """业绩报表 (``stock_yjbb_em(date=)``) — quarterly bulk performance summary."""

    __tablename__ = "earnings_report"
    __table_args__ = (
        UniqueConstraint("code", "report_period", name="uq_earnings_code_period"),
        Index("ix_earnings_period", "report_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    report_period: Mapped[str] = mapped_column(String(16))
    revenue: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_yoy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_profit_yoy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    eps: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    roe: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    gross_margin: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    disclose_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class Disclosure(Base, TimestampMixin):
    """公告披露 (``stock_notice_report`` + ``stock_zh_a_disclosure_report_cninfo``)."""

    __tablename__ = "disclosure"
    __table_args__ = (
        UniqueConstraint("code", "ann_date", "title", name="uq_disclosure_code_date_title"),
        Index("ix_disclosure_code", "code"),
        Index("ix_disclosure_ann_date", "ann_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ann_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(512))
    category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)   # 财务报告/重大事项/...
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="cninfo")            # cninfo|em
