"""Startup bootstrap: seed default users (dev convenience).

Creates an ``admin`` and an ``analyst`` account only when the User table is empty.
The admin password comes from ``DEFAULT_ADMIN_PASSWORD`` (default "admin123") — change it
in production. This keeps Phase-1 usable before full user management lands in Phase 2.
"""
from __future__ import annotations

import os

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.system import User

logger = get_logger(__name__)


def ensure_default_users(session: Session) -> None:
    count = session.scalar(select(func.count()).select_from(User)) or 0
    if count > 0:
        return
    admin_pw = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")
    session.add(User(username="admin", password_hash=hash_password(admin_pw),
                     role="admin", display_name="管理员"))
    session.add(User(username="analyst", password_hash=hash_password("analyst123"),
                     role="analyst", display_name="分析师"))
    session.commit()
    logger.warning("Seeded default users: admin / analyst. Set DEFAULT_ADMIN_PASSWORD in production.")
