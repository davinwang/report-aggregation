"""资讯舆情 (news) read helpers — list + summary for the /news page and MCP tool."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.news import NewsItem
from app.models.system import DataFreshness

SENTIMENTS = ("利好", "中性", "利空")


def latest_news_date(session: Session) -> date | None:
    """Newest stored publish date (the reference for relative windows)."""
    return session.scalar(select(func.max(NewsItem.publish_date)))


def list_news(
    session: Session,
    q: str | None = None,
    sentiment: str | None = None,
    source: str | None = None,
    start: date | None = None,
    end: date | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Filtered, newest-first page of flash news; returns (rows, total)."""
    where = []
    if q:
        like = f"%{q}%"
        where.append(or_(NewsItem.title.like(like), NewsItem.content.like(like)))
    if sentiment in SENTIMENTS:
        where.append(NewsItem.sentiment == sentiment)
    if source:
        where.append(NewsItem.source == source)
    if start:
        where.append(NewsItem.publish_date >= start)
    if end:
        where.append(NewsItem.publish_date <= end)

    total = session.scalar(select(func.count()).select_from(NewsItem).where(*where)) or 0
    rows = session.scalars(
        select(NewsItem).where(*where)
        .order_by(NewsItem.publish_at.desc(), NewsItem.id.desc())
        .offset((page - 1) * size).limit(size)
    ).all()
    return [_row(r) for r in rows], total


def summary(session: Session, days: int = 1) -> dict[str, Any]:
    """Sentiment counts + per-day series over the last ``days`` (page stat cards)."""
    ref = latest_news_date(session)
    payload: dict[str, Any] = {
        "ref": ref.isoformat() if ref else None,
        "days": days,
        "total": 0,
        "by_sentiment": {},
        "by_date": [],
        "freshness": _freshness(session),
    }
    if ref is None:
        return payload

    since = ref - timedelta(days=max(0, days - 1))
    rows = session.execute(
        select(NewsItem.publish_date, NewsItem.sentiment, func.count())
        .where(NewsItem.publish_date >= since)
        .group_by(NewsItem.publish_date, NewsItem.sentiment)
    ).all()

    by_sentiment: dict[str, int] = {}
    by_date_map: dict[date, dict[str, int]] = {}
    for d, s, n in rows:
        label = s or "中性"
        by_sentiment[label] = by_sentiment.get(label, 0) + n
        by_date_map.setdefault(d, {})[label] = n
    payload["by_sentiment"] = by_sentiment
    payload["total"] = sum(by_sentiment.values())
    payload["by_date"] = [
        {"date": d.isoformat(), "total": sum(v.values()), **v}
        for d, v in sorted(by_date_map.items())
    ]
    return payload


def _row(r: NewsItem) -> dict[str, Any]:
    return {
        "id": r.id,
        "source": r.source,
        "title": r.title,
        "content": r.content,
        "url": r.url,
        "publish_date": r.publish_date.isoformat(),
        "publish_at": r.publish_at.isoformat(sep=" "),
        "sentiment": r.sentiment,
        "sentiment_score": r.sentiment_score,
        "related_codes": r.related_codes or [],
    }


def _freshness(session: Session) -> dict[str, Any] | None:
    f = session.scalar(select(DataFreshness).where(DataFreshness.feed == "news_flash"))
    if f is None:
        return None
    return {
        "feed": f.feed,
        "last_success_at": f.last_success_at.isoformat() if f.last_success_at else None,
        "latest_data_date": f.latest_data_date.isoformat() if f.latest_data_date else None,
        "rows_total": f.rows_total,
        "weeks_behind": f.weeks_behind,
    }
