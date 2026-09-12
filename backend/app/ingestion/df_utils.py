"""DataFrame helpers — AkShare column names vary by source/version, so adapters
resolve columns by candidate names instead of hard-coding positions."""
from __future__ import annotations

from typing import Any, Optional


def pick_col(df, *candidates: str) -> Optional[str]:
    """Return the first column whose name matches any candidate (exact, then contains)."""
    if df is None or not hasattr(df, "columns"):
        return None
    cols = list(df.columns)
    for cand in candidates:
        if cand in cols:
            return cand
    for cand in candidates:
        for c in cols:
            if cand in str(c):
                return c
    return None


def get(row: Any, *candidates: str, default: Any = None) -> Any:
    """Get a value from a dict/Series by the first present candidate key."""
    for cand in candidates:
        try:
            if cand in row and row[cand] is not None:
                return row[cand]
        except TypeError:
            val = getattr(row, cand, None)
            if val is not None:
                return val
    return default


def get_contains(row: Any, *substrings: str, default: Any = None) -> Any:
    """Get a value whose column name *contains* the first matching substring.

    Useful for verbose, version-drifted Chinese column names like
    ``摊薄每股收益(元)`` / ``净资产收益率(%)``.
    """
    try:
        keys = list(row.keys())
    except AttributeError:
        keys = list(getattr(row, "index", []))
    for sub in substrings:
        for k in keys:
            if sub in str(k):
                try:
                    v = row[k]
                except Exception:  # noqa: BLE001
                    v = None
                if v is not None:
                    return v
    return default


def records(df) -> list[dict]:
    """Safe ``df.to_dict('records')`` returning [] for None/empty frames."""
    if df is None or not hasattr(df, "empty"):
        return []
    try:
        if df.empty:
            return []
        return df.to_dict("records")
    except Exception:  # noqa: BLE001
        return []


def has_cols(df) -> bool:
    return df is not None and hasattr(df, "columns") and len(df.columns) > 0
