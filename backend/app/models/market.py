"""Market data: daily bars (stocks & indices), index futures, index options.

``DailyQuote`` stores both stock and index bars (differentiated via Security.type);
the composite index ``(security_id, trade_date)`` backs the K-line/technical endpoints.
Stock index futures carry ``oi`` (持仓量) and a computed ``basis`` vs. the spot index.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import (
    Date,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DailyQuote(Base):
    __tablename__ = "daily_quote"
    __table_args__ = (
        UniqueConstraint("security_id", "trade_date", "adjust", name="uq_daily_quote_sec_date_adj"),
        Index("ix_daily_quote_sec_date", "security_id", "trade_date"),
        Index("ix_daily_quote_date", "trade_date"),
        # Hot read paths (K-line tails, 全市场速览 matrix, 板块联动 beta): the composite
        # (code, adjust, trade_date) turns per-symbol tail loads into pure index seeks;
        # (code, trade_date) covers MAX(trade_date)-per-code picks; (adjust, code, close)
        # covers the qfq count-per-code scan. Without these each query sorted ~750 rows.
        Index("ix_daily_quote_code_adj_date", "code", "adjust", "trade_date"),
        Index("ix_daily_quote_code_date", "code", "trade_date"),
        Index("ix_daily_quote_adj_code_close", "adjust", "code", "close"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[int] = mapped_column(Integer, index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)     # denormalized for fast queries
    trade_date: Mapped[date] = mapped_column(Date)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    pre_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)      # 成交量(手/股)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)      # 成交额(元)
    turnover_rate: Mapped[float | None] = mapped_column(Float, nullable=True)  # 换手率(%)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjust: Mapped[str] = mapped_column(String(8), default="qfq")   # ""|qfq|hfq
    source: Mapped[str] = mapped_column(String(16), default="em")


class IndexFutureDaily(Base, TimestampMixin):
    """中金所股指期货日线 (IF/IH/IC/IM) via ``get_futures_daily(market="CFFEX")``.

    ``basis`` = settle − underlying_index_close; ``basis_annualized`` computed in
    ``services.basis``.
    """

    __tablename__ = "index_future_daily"
    __table_args__ = (
        UniqueConstraint("symbol", "trade_date", name="uq_index_future_symbol_date"),
        Index("ix_index_future_variety_date", "variety", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)     # e.g. "IF2412"
    variety: Mapped[str] = mapped_column(String(8), index=True)      # IF|IH|IC|IM
    trade_date: Mapped[date] = mapped_column(Date)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    settle: Mapped[float | None] = mapped_column(Float, nullable=True)
    pre_settle: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    oi: Mapped[float | None] = mapped_column(Float, nullable=True)   # 持仓量
    turnover: Mapped[float | None] = mapped_column(Float, nullable=True)
    underlying_index: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 000300 etc.
    underlying_index_close: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis: Mapped[float | None] = mapped_column(Float, nullable=True)
    basis_annualized: Mapped[float | None] = mapped_column(Float, nullable=True)


class OptionQuote(Base, TimestampMixin):
    """股指期权/ETF期权 T型报价 via ``option_finance_board``."""

    __tablename__ = "option_quote"
    __table_args__ = (
        UniqueConstraint("contract_code", "trade_date", name="uq_option_contract_date"),
        Index("ix_option_underlying_date", "underlying", "trade_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    underlying: Mapped[str] = mapped_column(String(32), index=True)   # 沪深300股指期权 / 中证1000股指期权 ...
    end_month: Mapped[str | None] = mapped_column(String(8), nullable=True)  # e.g. "2412"
    contract_code: Mapped[str] = mapped_column(String(32), index=True)
    trade_date: Mapped[date] = mapped_column(Date)
    strike: Mapped[float | None] = mapped_column(Float, nullable=True)
    cp: Mapped[str | None] = mapped_column(String(8), nullable=True)   # call|put
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    settle: Mapped[float | None] = mapped_column(Float, nullable=True)
    pre_settle: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    oi: Mapped[float | None] = mapped_column(Float, nullable=True)
    iv: Mapped[float | None] = mapped_column(Float, nullable=True)     # 隐含波动率
    delta: Mapped[float | None] = mapped_column(Float, nullable=True)
