"""Portable bulk-upsert helpers (SQLite + PostgreSQL).

Dialect-specific ``INSERT ... ON CONFLICT`` differs between backends, so we use a
load-then-diff strategy that is correct everywhere and fast enough for feed-sized
batches: pull the existing rows for a bounded scope into a dict keyed by the natural
key, then update-or-insert in memory and flush in batches.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger

logger = get_logger(__name__)

BATCH = 500


def _key_of(row: dict[str, Any], key_fields: Sequence[str]) -> tuple:
    return tuple(row.get(f) for f in key_fields)


def bulk_upsert(
    session: Session,
    model: type,
    rows: Iterable[dict[str, Any]],
    key_fields: Sequence[str],
    scope: Select | None = None,
    mutable_fields: Sequence[str] | None = None,
) -> int:
    """Upsert ``rows`` into ``model`` keyed by ``key_fields``.

    Args:
        scope: optional pre-filtered SELECT to load existing rows (bounds memory). If
            None, existing rows are looked up per unique key via IN-clauses on the first
            key field.
        mutable_fields: fields to update on conflict; defaults to all non-key fields.

    Returns: number of rows inserted + updated.
    """
    rows = list(rows)
    if not rows:
        return 0

    key_fields = list(key_fields)
    all_fields = list(rows[0].keys())
    update_fields = list(mutable_fields) if mutable_fields else [f for f in all_fields if f not in key_fields]

    # Build index of existing rows.
    existing: dict[tuple, Any] = {}
    if scope is not None:
        for obj in session.scalars(scope).all():
            existing[tuple(getattr(obj, f) for f in key_fields)] = obj
    else:
        # Fall back to IN-clause on the first key field to bound the query.
        first_field = key_fields[0]
        candidates = {r.get(first_field) for r in rows if r.get(first_field) is not None}
        for chunk in _chunked(sorted(candidates, key=str), BATCH):
            q = select(model).where(getattr(model, first_field).in_(chunk))
            for obj in session.scalars(q).all():
                existing[tuple(getattr(obj, f) for f in key_fields)] = obj

    _SENTINEL = object()  # marks rows added in this batch (no persistent obj yet)

    touched = 0
    pending_new = 0
    for row in rows:
        k = _key_of(row, key_fields)
        obj = existing.get(k, _SENTINEL)
        if obj is _SENTINEL:
            # Key not seen before (neither in DB nor earlier in this batch).
            session.add(model(**row))
            pending_new += 1
            touched += 1
            existing[k] = None  # sentinel: added this batch, no persistent obj yet
        elif obj is None:
            # Duplicate within the same batch — skip (first occurrence already added).
            continue
        else:
            changed = False
            for f in update_fields:
                if f in row and getattr(obj, f) != row[f]:
                    setattr(obj, f, row[f])
                    changed = True
            if changed:
                touched += 1
        if pending_new and pending_new % BATCH == 0:
            session.flush()
    session.flush()
    return touched


def _chunked(seq: Sequence, size: int) -> Iterable[Sequence]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]
