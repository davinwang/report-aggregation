"""Model building blocks: Base re-export, common mixins, and domain enums.

Conventions:
- Integer autoincrement primary keys (simple, portable across SQLite/Postgres).
- Naive UTC datetimes (SQLite has no tz storage); use ``utcnow()``.
- ``JSON`` columns for wide/variable payloads (financial statement rows, forecasts).
"""
from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

__all__ = [
    "Base",
    "utcnow",
    "TimestampMixin",
    "SecurityType",
    "StatementType",
    "RatingDirection",
]


def utcnow() -> datetime:
    """Naive UTC now (consistent storage across backends)."""
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


# ``(str, Enum)`` rather than ``enum.StrEnum`` (ruff UP042) is deliberate and load-bearing.
# On Python 3.11+ ``f"{RatingDirection.buy}"`` on a ``(str, Enum)`` member renders
# ``'RatingDirection.buy'``, whereas ``StrEnum`` renders ``'买入'``. These members are
# interpolated into ``Signal.reason``, a column that is **persisted and shown in the UI**
# (``services/signals.py``), so switching would rewrite what already-stored rows render as
# and diverge from rows written before the change. That is a data-compatibility decision,
# not a lint fix — raise it as its own change with a backfill for existing rows.


class SecurityType(str, enum.Enum):  # noqa: UP042
    """Tradable/quotable instrument kinds.

    ``etf`` and ``bond`` (可转债) share the ``daily_quote`` table with stocks and
    indices — they are only distinguished for the sidebar/universe filters, so
    widening this enum needs no schema migration (``security.type`` is a plain string).
    """

    stock = "stock"
    index = "index"
    etf = "etf"
    bond = "bond"
    future = "future"
    option = "option"


class StatementType(str, enum.Enum):  # noqa: UP042
    balance = "balance"
    income = "income"
    cashflow = "cashflow"


class RatingDirection(str, enum.Enum):  # noqa: UP042
    """Normalized stock rating buckets (transform of futures 利多/利空)."""

    buy = "买入"
    overweight = "增持"
    neutral = "中性"
    underweight = "减持"
    sell = "卖出"
    unknown = "未评级"
