"""Research reports, ratings, derived signals, accuracy and weekly stats.

These are the heart of the platform (研报库 / 可操作信号 / 研报准确率 / 周统计).
``ResearchReport`` holds full report rows (title/org/analyst/rating/target/PDF);
``RatingEvent`` holds the bulk daily ratings feed; ``Signal`` and ``AccuracySnapshot``
are derived by services (no LLM in MVP — rule-based).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Boolean, Date, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ResearchReport(Base, TimestampMixin):
    """个股研报 (``stock_research_report_em``) + normalized rating history."""

    __tablename__ = "research_report"
    __table_args__ = (
        UniqueConstraint("code", "title", "org", "publish_date", name="uq_report_code_title_org_date"),
        Index("ix_report_publish_date", "publish_date"),
        Index("ix_report_org", "org"),
        Index("ix_report_code", "code"),
        Index("ix_report_industry_group", "industry_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    org: Mapped[str | None] = mapped_column(String(128), nullable=True)        # 机构
    analysts: Mapped[str | None] = mapped_column(String(256), nullable=True)   # 分析师(逗号分隔)
    rating: Mapped[str | None] = mapped_column(String(32), nullable=True)      # 东财评级/投资评级
    prev_rating: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rating_change: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 上调/下调/维持/首次
    is_first: Mapped[bool] = mapped_column(Boolean, default=False)
    target_price_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_price_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)    # 申万/东财行业
    industry_group: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publish_date: Mapped[date] = mapped_column(Date)
    report_count_1m: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 近一月个股研报数
    pdf_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    forecast_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)     # 盈利预测(收益/PE by year)
    source: Mapped[str] = mapped_column(String(16), default="em")                  # em|cninfo|sina
    ingested_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class RatingEvent(Base):
    """Bulk daily ratings feed (``stock_rank_forecast_cninfo(date=)``).

    One row per (security, org, analyst, date) rating action. Feeds 可操作信号 + 研报准确率.
    """

    __tablename__ = "rating_event"
    __table_args__ = (
        UniqueConstraint("code", "org", "analyst", "trade_date", name="uq_rating_code_org_analyst_date"),
        Index("ix_rating_trade_date", "trade_date"),
        Index("ix_rating_org", "org"),
        Index("ix_rating_code", "code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date)
    org: Mapped[str | None] = mapped_column(String(128), nullable=True)
    analyst: Mapped[str | None] = mapped_column(String(256), nullable=True)
    rating: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rating_norm: Mapped[str | None] = mapped_column(String(16), nullable=True)   # buy/overweight/...
    prev_rating: Mapped[str | None] = mapped_column(String(32), nullable=True)
    rating_change: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_first: Mapped[bool] = mapped_column(Boolean, default=False)
    target_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="cninfo")


class Signal(Base, TimestampMixin):
    """可操作信号 — rule-based derivation from ratings/target-price/consensus (no LLM)."""

    __tablename__ = "signal"
    __table_args__ = (
        UniqueConstraint("code", "trade_date", "kind", name="uq_signal_code_date_kind"),
        Index("ix_signal_trade_date", "trade_date"),
        Index("ix_signal_direction", "direction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date)
    # rating|upgrade|downgrade|target|consensus
    kind: Mapped[str] = mapped_column(String(32), default="rating")
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)  # buy/overweight/neutral/...
    strength: Mapped[str | None] = mapped_column(String(8), nullable=True)     # 弱|中|强
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sources_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    industry_group: Mapped[str | None] = mapped_column(String(32), nullable=True)


class RecommendPool(Base, TimestampMixin):
    """机构推荐池 (新浪 stock_institute_recommend) — 上调/下调/首次评级名单.

    Independent of ``Signal``: ``refresh_signals`` deterministically rebuilds the
    Signal window (delete + reinsert), so the pool must not live there or every
    signal refresh would wipe it.
    """

    __tablename__ = "recommend_pool"
    __table_args__ = (
        UniqueConstraint("code", "trade_date", "kind", name="uq_pool_code_date_kind"),
        Index("ix_pool_trade_date", "trade_date"),
        Index("ix_pool_kind", "kind"),
        Index("ix_pool_code", "code"),
        Index("ix_pool_industry_group", "industry_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    security_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trade_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16))              # upgrade|downgrade|first
    rating: Mapped[str | None] = mapped_column(String(32), nullable=True)   # 最新评级
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    strength: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 弱|中|强
    org: Mapped[str | None] = mapped_column(String(128), nullable=True)
    analysts: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(64), nullable=True)
    industry_group: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="sina")            # sina
    sources_json: Mapped[list | None] = mapped_column(JSON, nullable=True)


class AccuracySnapshot(Base, TimestampMixin):
    """研报准确率 — per-org/analyst hit-rate & net-skill for a period."""

    __tablename__ = "accuracy_snapshot"
    __table_args__ = (
        UniqueConstraint("period_type", "period_key", "subject_type", "subject",
                         name="uq_acc_period_subject"),
        Index("ix_acc_period", "period_type", "period_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_type: Mapped[str] = mapped_column(String(16))   # weekly|monthly
    period_key: Mapped[str] = mapped_column(String(32))    # e.g. "2026-09-10" (week ending)
    subject_type: Mapped[str] = mapped_column(String(16))  # org|analyst
    subject: Mapped[str] = mapped_column(String(256), index=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    hit_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_skill: Mapped[float | None] = mapped_column(Float, nullable=True)
    prev_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    horizon_days: Mapped[int] = mapped_column(Integer, default=20)


class WeeklyStat(Base, TimestampMixin):
    """周统计 Tab2 — per-org article counts across industry groups for a week."""

    __tablename__ = "weekly_stat"
    __table_args__ = (
        UniqueConstraint("week_key", "org", name="uq_weekly_week_org"),
        Index("ix_weekly_week", "week_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_key: Mapped[str] = mapped_column(String(32))     # week-ending date
    org: Mapped[str] = mapped_column(String(128))
    total: Mapped[int] = mapped_column(Integer, default=0)
    by_group_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # {group: count}


class PeerActivity(Base, TimestampMixin):
    """周统计 Tab1 — 友商报告与活动 (manually uploaded via /contrib)."""

    __tablename__ = "peer_activity"
    __table_args__ = (Index("ix_peer_period", "period_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    period_key: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(16), default="report")   # report|event
    industry_group: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    covered_by_us: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # 本公司是否覆盖
    url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
