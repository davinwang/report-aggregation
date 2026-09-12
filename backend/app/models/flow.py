"""Capital-flow & sentiment data (资金流向) — Phase 2 module, tables defined up-front."""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import JSON, Date, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class FundFlowDaily(Base):
    """个股资金流 (``stock_individual_fund_flow``)."""

    __tablename__ = "fund_flow_daily"
    __table_args__ = (
        UniqueConstraint("code", "trade_date", name="uq_fundflow_code_date"),
        Index("ix_fundflow_date", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16))
    trade_date: Mapped[date] = mapped_column(Date)
    close: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    main_net_inflow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)     # 主力净流入
    main_net_inflow_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    super_large_net: Mapped[Optional[float]] = mapped_column(Float, nullable=True)     # 超大单
    large_net: Mapped[Optional[float]] = mapped_column(Float, nullable=True)           # 大单
    medium_net: Mapped[Optional[float]] = mapped_column(Float, nullable=True)          # 中单
    small_net: Mapped[Optional[float]] = mapped_column(Float, nullable=True)           # 小单


class NorthboundDaily(Base, TimestampMixin):
    """北向资金 (``stock_hsgt_fund_flow_summary_em``)."""

    __tablename__ = "northbound_daily"
    __table_args__ = (UniqueConstraint("trade_date", "board", name="uq_north_date_board"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    board: Mapped[str] = mapped_column(String(16), default="north")   # north|沪股通|深股通
    net_inflow: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    extra_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class MarginData(Base, TimestampMixin):
    """融资融券 (``stock_margin_sse`` / ``stock_margin_detail_sse``)."""

    __tablename__ = "margin_data"
    __table_args__ = (
        UniqueConstraint("exchange", "code", "trade_date", name="uq_margin_exch_code_date"),
        Index("ix_margin_date", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exchange: Mapped[str] = mapped_column(String(16))     # SSE|SZSE
    code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # null = market summary
    trade_date: Mapped[date] = mapped_column(Date)
    rzye: Mapped[Optional[float]] = mapped_column(Float, nullable=True)      # 融资余额
    rzmre: Mapped[Optional[float]] = mapped_column(Float, nullable=True)     # 融资买入额
    rqye: Mapped[Optional[float]] = mapped_column(Float, nullable=True)      # 融券余额
    rzrqye: Mapped[Optional[float]] = mapped_column(Float, nullable=True)    # 融资融券余额


class LhbRecord(Base, TimestampMixin):
    """龙虎榜 (``stock_lhb_detail_em``)."""

    __tablename__ = "lhb_record"
    __table_args__ = (
        UniqueConstraint("code", "trade_date", "reason", name="uq_lhb_code_date_reason"),
        Index("ix_lhb_date", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date)
    reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    close: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    buy_amt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sell_amt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    net_amt: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    turnover: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
