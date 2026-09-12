"""Common API helpers: response envelope, pagination, and date parsing.

Every read endpoint returns ``{"data": ..., "meta": {...}}`` so the frontend has a
uniform shape carrying pagination + data-freshness ("新鲜度") provenance.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def envelope(data: Any, **meta: Any) -> dict:
    return {"data": data, "meta": meta}


def paged(data: Any, total: int, page: int, size: int, **extra: Any) -> dict:
    return {
        "data": data,
        "meta": {"total": total, "page": page, "size": size, "pages": (total + size - 1) // size if size else 0, **extra},
    }


def parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def clamp_page(page: int, size: int) -> tuple[int, int]:
    page = max(1, page or 1)
    size = min(max(1, size or 20), 200)
    return page, size
