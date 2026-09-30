"""news_flash — 全球财经快讯 via 东财快讯 + 财联社电报 (bulk, no symbol loop).

Two upstreams with per-source isolation (one dead source never aborts the run —
only a total failure raises, so base retry/backoff and error status still work):
``stock_info_global_em`` (200 rows/call) and ``stock_info_global_cls`` (latest
20 rows/call). Rows are deduped by ``(source, publish_at, title)`` and annotated
with a rule-based 情绪 score plus 关联个股 matched from security names (title
hits first, content fills up, capped at 5).
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.ingestion import sentiment
from app.ingestion.akshare_client import get_ak
from app.ingestion.base import BaseAdapter, bulk_upsert
from app.ingestion.df_utils import get, records
from app.ingestion.normalizers import clean_text, to_date
from app.models.news import NewsItem
from app.models.security import Security

logger = get_logger(__name__)

_CONTENT_CAP = 2000   # store bounded content (flash bodies are short anyway)
_MAX_RELATED = 5      # 关联个股 cap per item
_MIN_NAME_LEN = 2     # skip 1-char names (too noisy for substring matching)

#: display labels for the ``source`` codes.
SOURCE_LABELS = {"em": "东财快讯", "cls": "财联社"}


class NewsFlashAdapter(BaseAdapter):
    name = "news_flash"
    description = "全球财经快讯 (东财快讯/财联社电报)"
    per_symbol = False

    # ---- fetch: two sources, per-source isolation -------------------------
    def fetch(self, **kwargs) -> dict[str, Any]:
        ak = get_ak()
        out: dict[str, Any] = {"em": None, "cls": None}
        errors: list[str] = []
        calls = (
            ("em", lambda: ak.stock_info_global_em()),
            ("cls", lambda: ak.stock_info_global_cls(symbol="全部")),
        )
        for key, fn in calls:
            try:
                out[key] = fn()
            except Exception as exc:  # noqa: BLE001 - one dead source must not abort the run
                errors.append(f"{key}: {exc}")
                logger.warning("[%s] source '%s' failed: %s", self.name, key, exc)
        if out["em"] is None and out["cls"] is None and errors:
            raise RuntimeError("all news sources failed: " + "; ".join(errors))
        return out

    # ---- normalize ---------------------------------------------------------
    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if isinstance(raw, dict):
            rows.extend(self._normalize_em(raw.get("em")))
            rows.extend(self._normalize_cls(raw.get("cls")))
        seen: set[tuple] = set()
        out: list[dict[str, Any]] = []
        for r in rows:
            key = (r["source"], r["publish_at"], r["title"])
            if key in seen:  # intra-batch duplicate (same flash across fetches)
                continue
            seen.add(key)
            out.append(r)
        return out

    def _normalize_em(self, frame: Any) -> list[dict[str, Any]]:
        """东财快讯: 标题/摘要/发布时间(str)/链接."""
        rows: list[dict[str, Any]] = []
        for r in records(frame):
            title = clean_text(get(r, "标题"))
            content = clean_text(get(r, "摘要", "内容"))
            dt = _to_dt(get(r, "发布时间"))
            if not title or dt is None:
                continue
            label, score = sentiment.classify(f"{title} {content or ''}")
            rows.append({
                "source": "em",
                "title": title[:512],
                "content": (content or "")[:_CONTENT_CAP] or None,
                "url": clean_text(get(r, "链接")),
                "publish_date": dt.date(),
                "publish_at": dt,
                "sentiment": label,
                "sentiment_score": score,
            })
        return rows

    def _normalize_cls(self, frame: Any) -> list[dict[str, Any]]:
        """财联社电报: 标题(可空)/内容/发布日期(date)/发布时间(time)."""
        rows: list[dict[str, Any]] = []
        for r in records(frame):
            title = clean_text(get(r, "标题"))
            content = clean_text(get(r, "内容"))
            dt = _to_dt(get(r, "发布时间"), get(r, "发布日期"))
            if dt is None:
                continue
            if not title:  # some flashes carry only 内容
                title = (content or "")[:60]
            if not title:
                continue
            label, score = sentiment.classify(f"{title} {content or ''}")
            rows.append({
                "source": "cls",
                "title": title[:512],
                "content": (content or "")[:_CONTENT_CAP] or None,
                "url": None,
                "publish_date": dt.date(),
                "publish_at": dt,
                "sentiment": label,
                "sentiment_score": score,
            })
        return rows

    # ---- persist ------------------------------------------------------------
    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        if not rows:
            return 0
        name_map = _stock_name_map(session)
        if name_map:
            names = sorted(name_map, key=len, reverse=True)  # longer/specific names first
            for r in rows:
                r["related_codes"] = _match_symbols(
                    r.get("title") or "", r.get("content") or "", names, name_map
                )
        dates = [r["publish_date"] for r in rows]
        scope = select(NewsItem).where(
            NewsItem.publish_date >= min(dates), NewsItem.publish_date <= max(dates)
        )
        return bulk_upsert(
            session, NewsItem, rows,
            key_fields=["source", "publish_at", "title"],
            scope=scope,
            mutable_fields=["content", "url", "sentiment", "sentiment_score", "related_codes"],
        )


def _to_dt(primary: Any, secondary: Any = None) -> datetime | None:
    """Parse the publish timestamp from either source shape.

    EM: a datetime string ("2026-09-16 14:30:00") as ``primary``.
    CLS: ``time`` as primary + ``date`` as secondary.
    """
    t_part: time | None = None
    d_part: date | None = None
    dt_part: datetime | None = None

    def feed(v: Any) -> None:
        nonlocal t_part, d_part, dt_part
        if v is None or dt_part is not None:
            return
        if isinstance(v, datetime):
            dt_part = v
        elif isinstance(v, time):
            t_part = v
        elif isinstance(v, date):
            d_part = v
        else:
            s = str(v).strip()
            if not s:
                return
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y%m%d %H:%M:%S"):
                try:
                    dt_part = datetime.strptime(s, fmt)
                    return
                except ValueError:
                    continue
            parsed = to_date(s)  # date-only fallback
            if parsed is not None and d_part is None:
                d_part = parsed

    feed(primary)
    feed(secondary)
    if dt_part is not None:
        return dt_part
    if d_part is not None:
        return datetime.combine(d_part, t_part or time(0, 0))
    return None


def _stock_name_map(session: Session) -> dict[str, str]:
    """{name -> code} for A-share securities with matchable names."""
    rows = session.execute(
        select(Security.name, Security.code).where(Security.type == "stock", Security.name != "")
    ).all()
    return {name: code for name, code in rows if name and len(name) >= _MIN_NAME_LEN}


def _match_symbols(
    title: str, content: str, names: list[str], name_map: dict[str, str],
) -> list[dict[str, str]]:
    """关联个股: title hits first, content fills up, capped at ``_MAX_RELATED``."""
    picked = [n for n in names if n in title][:_MAX_RELATED]
    if len(picked) < _MAX_RELATED:
        picked += [
            n for n in names if n not in picked and n in content
        ][:_MAX_RELATED - len(picked)]
    return [{"code": name_map[n], "name": n} for n in picked]


adapter = NewsFlashAdapter()
