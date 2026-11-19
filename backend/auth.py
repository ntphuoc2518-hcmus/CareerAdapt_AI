"""Session-cookie authentication and role-based access control."""
from __future__ import annotations

import os
import sys
import uuid
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from backend.accounts import get_session


def session_cookie_name() -> str:
    if os.getenv("CAREERADAPT_ENV", "development").lower() == "production":
        return "__Host-careeradapt_session"
    return "careeradapt_session"


class AuthenticatedUser(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str


def legacy_demo_auth_enabled() -> bool:
    """Keep fixture tokens confined to tests or an explicit local demo opt-in."""
    demo_requested = os.getenv("CAREERADAPT_DEMO_AUTH", "").lower() == "true"
    local_demo_allowed = os.getenv("CAREERADAPT_ENV", "development").lower() != "production"
    return "pytest" in sys.modules or (demo_requested and local_demo_allowed)


def get_current_user(request: Request) -> AuthenticatedUser:
    """Authenticate through an opaque, server-side session cookie."""
    # The request middleware already resolved the user (to lock and refresh their data); reuse it.
    known = getattr(request.state, "careeradapt_user", None)
    if known is not None:
        return known
    user = resolve_user(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
    return user


def resolve_user(request: Request) -> Optional[AuthenticatedUser]:
    """The signed-in user of a request, or None. Never raises."""
    token = request.cookies.get(session_cookie_name())
    account = get_session(token) if token else None
    if account is None:
        # The legacy role-switch demo is opt-in for isolated local demos only.
        if legacy_demo_auth_enabled():
            authorization = request.headers.get("authorization", "")
            demo_users = {
                "token_student_1": ("11111111-1111-1111-1111-111111111111", "student1@hcmus.edu.vn", "Nguyễn Văn Sinh Viên (SV1)", "student"),
                "token_student_2": ("22222222-2222-2222-2222-222222222222", "student2@hcmus.edu.vn", "Trần Thị Lan (SV2)", "student"),
                "token_admin": ("99999999-9999-9999-9999-999999999999", "admin@hcmus.edu.vn", "Quản Trị Viên / Giảng Viên", "admin"),
            }
            parts = authorization.split()
            demo = demo_users.get(parts[1]) if len(parts) == 2 and parts[0].lower() == "bearer" else None
            if demo:
                return AuthenticatedUser(user_id=uuid.UUID(demo[0]), email=demo[1], full_name=demo[2], role=demo[3])
        return None
    return AuthenticatedUser(user_id=uuid.UUID(account["id"]), email=account["email"], full_name=account["full_name"], role=account["role"])


def require_admin_user(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Require an administrator role assigned by the server."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chức năng yêu cầu quyền Quản trị viên (Admin).")
    return current_user
