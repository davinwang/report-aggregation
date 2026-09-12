"""Universe resolution for per-symbol feeds.

Per-symbol ingestion (research reports, financials, price history) is bounded to a
configurable universe instead of all ~5000 A-shares. Default is 沪深300; supports
``hs300``, ``zz500``, ``hs300+zz500``, ``all`` (all active stock Securities in DB),
or a comma-separated explicit code list.

Constituent lists are fetched from AkShare and cached to ``data/universe_<name>.json``
for ``CACHE_DAYS`` to avoid repeated upstream calls.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, settings
from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.akshare_client import AkShareUnavailable, get_ak
from app.ingestion.normalizers import norm_code

logger = get_logger(__name__)

CACHE_DIR = BACKEND_DIR.parent / "data"
CACHE_DAYS = 7

# index code per universe token
_INDEX_CODES = {"hs300": "000300", "zz500": "000905", "zz1000": "000852", "sz50": "000016"}


def _cache_path(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"universe_{name}.json"


def _read_cache(name: str) -> Optional[list[str]]:
    p = _cache_path(name)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
        saved = datetime.fromisoformat(payload["saved_at"])
        if datetime.now() - saved > timedelta(days=CACHE_DAYS):
            return None
        codes = [c for c in payload["codes"] if c]
        return codes or None
    except Exception:  # noqa: BLE001
        return None


def _write_cache(name: str, codes: list[str]) -> None:
    try:
        _cache_path(name).write_text(
            json.dumps({"saved_at": datetime.now().isoformat(), "codes": codes}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        logger.warning("could not write universe cache for %s", name)


def _extract_codes(df) -> list[str]:
    """Pull 6-digit codes from a constituent DataFrame regardless of column naming."""
    codes: list[str] = []
    if df is None or not hasattr(df, "columns"):
        return codes
    # Prioritize columns that specifically hold constituent codes
    # (not the index code column which also matches generic patterns).
    priority_cols = [c for c in df.columns if re.search(r"成分|品种", str(c), re.I)]
    fallback_cols = [c for c in df.columns if re.search(r"代码|code", str(c), re.I) and c not in priority_cols]
    cols = (priority_cols or fallback_cols) or list(df.columns)
    for _, row in df.iterrows():
        for col in cols:
            c = norm_code(row.get(col))
            if c and re.fullmatch(r"\d{6}", c):
                codes.append(c)
                break
    # de-dup preserving order
    seen: set[str] = set()
    out = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _fetch_index_cons(index_code: str) -> list[str]:
    ak = get_ak()
    throttle.default_throttle.wait()
    last_exc: Optional[Exception] = None
    # Try the most stable interfaces first.
    for fn_name, kwargs in (
        ("index_stock_cons_csindex", {"symbol": index_code}),
        ("index_stock_cons_weight_csindex", {"symbol": index_code}),
        ("index_stock_cons", {"symbol": index_code}),
    ):
        fn = getattr(ak, fn_name, None)
        if fn is None:
            continue
        try:
            df = fn(**kwargs)
            codes = _extract_codes(df)
            if codes:
                logger.info("universe %s: %d codes via %s", index_code, len(codes), fn_name)
                return codes
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("universe fetch %s(%s) failed: %s", fn_name, index_code, exc)
    if last_exc:
        raise last_exc
    return []


def _resolve_token(token: str) -> list[str]:
    token = token.strip().lower()
    if token in _INDEX_CODES:
        cached = _read_cache(token)
        if cached:
            return cached
        try:
            codes = _fetch_index_cons(_INDEX_CODES[token])
        except AkShareUnavailable:
            logger.warning("akshare unavailable; cannot resolve universe '%s'", token)
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("failed to fetch constituents for %s: %s", token, exc)
            return []
        if codes:
            _write_cache(token, codes)
        return codes
    # explicit single code
    c = norm_code(token)
    return [c] if c else []


def resolve_universe(name: Optional[str] = None, session: Optional[Session] = None) -> list[str]:
    """Resolve a universe spec into a de-duplicated list of stock codes."""
    name = (name or settings.universe or "hs300").strip()

    if name == "all":
        if session is not None:
            from app.models.security import Security

            return list(session.scalars(select(Security.code).where(Security.type == "stock")).all())
        return []

    codes: list[str] = []
    for token in name.split("+"):
        codes.extend(_resolve_token(token))

    seen: set[str] = set()
    out = []
    for c in codes:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    logger.info("resolved universe '%s' -> %d codes", name, len(out))
    return out
