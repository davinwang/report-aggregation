"""System tables: users/auth, ingestion logs, data freshness, and reserved AI synthesis.

``IngestionLog`` + ``DataFreshness`` power ``/health/deep`` and the UI FreshnessBadge —
critical because AkShare interfaces can lag or break. ``AiSynthesis`` is created now but
only populated in Phase 3 (AI deferred, feature-flagged).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, utcnow


class User(Base, TimestampMixin):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("username", name="uq_user_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="viewer")   # admin|analyst|viewer
    display_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class IngestionLog(Base):
    """One row per feed run — status, row counts, latency, error text."""

    __tablename__ = "ingestion_log"
    __table_args__ = (Index("ix_ingest_feed_started", "feed", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")   # running|ok|error|partial
    rows_upserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_seen: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detail_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class DataFreshness(Base):
    """Latest successfully-ingested data date per feed (drives 新鲜度 badges)."""

    __tablename__ = "data_freshness"
    __table_args__ = (UniqueConstraint("feed", name="uq_freshness_feed"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feed: Mapped[str] = mapped_column(String(64), index=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    latest_data_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    weeks_behind: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)


class AiSynthesis(Base, TimestampMixin):
    """RESERVED (Phase 3). AI综合研判 / market synthesis output. Not populated in MVP."""

    __tablename__ = "ai_synthesis"
    __table_args__ = (Index("ix_ai_scope_period", "scope", "period_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(32), default="market")   # market|stock|sector|chat
    ref_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    period_key: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
