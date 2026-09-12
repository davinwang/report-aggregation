"""Helpers to map stock codes → Security rows (bulk, cached per call)."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.security import Security, group_of


def security_id_map(session: Session, codes: Iterable[str]) -> dict[str, int]:
    """Return {code: security_id} for the given codes (single query)."""
    codes = [c for c in dict.fromkeys(codes) if c]
    if not codes:
        return {}
    out: dict[str, int] = {}
    # Chunk IN-clause to stay within SQLite variable limits.
    for i in range(0, len(codes), 800):
        chunk = codes[i : i + 800]
        rows = session.execute(
            select(Security.code, Security.id).where(Security.code.in_(chunk))
        ).all()
        out.update({code: sid for code, sid in rows})
    return out


def industry_group_map(session: Session, codes: Iterable[str]) -> dict[str, str]:
    """Return {code: industry_group} for the given codes."""
    codes = [c for c in dict.fromkeys(codes) if c]
    if not codes:
        return {}
    out: dict[str, str] = {}
    for i in range(0, len(codes), 800):
        chunk = codes[i : i + 800]
        rows = session.execute(
            select(Security.code, Security.industry_sw).where(Security.code.in_(chunk))
        ).all()
        out.update({code: group_of(sw) for code, sw in rows})
    return out


def get_or_create_security(
    session: Session, code: str, name: str | None = None, type_: str = "stock", exchange: str = ""
) -> Security:
    sec = session.scalar(select(Security).where(Security.code == code))
    if sec is None:
        sec = Security(code=code, name=name or "", type=type_, exchange=exchange)
        session.add(sec)
        session.flush()
    elif name and not sec.name:
        sec.name = name
    return sec
