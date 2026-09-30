"""Auth & security (Phase 2 wiring, defined up-front so endpoints can depend on it).

- Password hashing uses stdlib ``hashlib.pbkdf2_hmac`` (no bcrypt native build pain on Windows).
- JWT via ``PyJWT`` (pure Python).
- FastAPI dependencies: ``get_current_user`` (optional) and ``require_admin`` (guard).

Read-only pages stay public (reference parity); only ``/contrib``, ``/admin``, ``/ops``
require auth, and admin-only routes use ``require_admin``.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db

_bearer = HTTPBearer(auto_error=False)

PBKDF2_ROUNDS = 120_000

# Synthetic admin returned when ``auth_enabled`` is False (login feature disabled).
_DEV_ADMIN = SimpleNamespace(id=0, username="admin", role="admin", display_name="管理员", is_active=True)


# ----------------------------- password hashing -----------------------------
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, salt_hex, dk_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ----------------------------- JWT -----------------------------
def create_access_token(subject: str, role: str = "viewer", expires_minutes: int | None = None) -> str:
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=expires_minutes or settings.jwt_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


# ----------------------------- FastAPI deps -----------------------------
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
):
    """Resolve the current user from a Bearer token, or ``None`` if anonymous.

    When ``settings.auth_enabled`` is False (login disabled), every request acts as a
    hardcoded admin so gated tools (/ops, /admin, /contrib) work without a login flow.
    Otherwise does not raise when anonymous — callers that require auth use ``require_user``.
    """
    if not settings.auth_enabled:
        return _DEV_ADMIN
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc}") from exc

    from app.models.user import User  # local import to avoid cycles

    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_user(user=Depends(get_current_user)):
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return user


def require_admin(user=Depends(get_current_user)):
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    if getattr(user, "role", None) != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required")
    return user
