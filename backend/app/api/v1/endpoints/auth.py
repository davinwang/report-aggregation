"""Auth endpoints (Phase 2) — login + current user.

Read-only pages stay public; ``/api/me`` returns an anonymous marker when not logged in
so the frontend can conditionally reveal contrib/admin/ops entries.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import create_access_token, get_current_user, verify_password
from app.models.system import User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已停用")
    token = create_access_token(subject=user.username, role=user.role)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me")
def me(user=Depends(get_current_user)) -> dict:
    if user is None:
        return {"data": {"authenticated": False}, "meta": {}}
    return {"data": {"authenticated": True, "user": UserOut.model_validate(user).model_dump()}, "meta": {}}
