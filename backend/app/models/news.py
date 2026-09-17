"""资讯舆情 — whole-market flash news (东财快讯 / 财联社电报).

``NewsItem`` stores one flash per (source, publish_at, title): rule-based 情绪
annotation (see ``ingestion/sentiment.py``) plus 关联个股 matched from security
names in ``NewsFlashAdapter.persist``. Read API in ``api/v1/endpoints/news.py``.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Date, DateTime, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NewsItem(Base, TimestampMixin):
    __tablename__ = "news_item"
    __table_args__ = (
        UniqueConstraint("source", "publish_at", "title", name="uq_news_source_pub_title"),
        Index("ix_news_publish", "publish_at", "id"),
        Index("ix_news_date", "publish_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(16))                 # em|cls
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    publish_date: Mapped[date] = mapped_column(Date)                # local (CST) date
    #: Local wall time; never null — it is part of the dedupe key.
    publish_at: Mapped[datetime] = mapped_column(DateTime)
    sentiment: Mapped[Optional[str]] = mapped_column(String(8), nullable=True, index=True)  # 利好|中性|利空
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    related_codes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # [{code, name}]
