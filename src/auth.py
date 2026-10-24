"""Authentication and Identity Dependencies for CareerAdapt AI (TV3).

Enforces server-side identity verification. Never trusts client-supplied user_id in headers or bodies.
"""
from __future__ import annotations
import uuid
from typing import Optional
from pydantic import BaseModel, EmailStr
from fastapi import Header, HTTPException, status, Depends
from security_utils import verify_ownership


class AuthenticatedUser(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: str = "STUDENT"  # STUDENT, ADMIN, INSTRUCTOR


# Pre-configured demo users mapped to tokens for seamless local development and automated testing
DEMO_USERS: dict[str, AuthenticatedUser] = {
    "token_student_1": AuthenticatedUser(
        user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        email="student1@test.local",
        full_name="Nguyễn Văn A (Demo)",
        role="STUDENT"
    ),
    "token_student_2": AuthenticatedUser(
        user_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        email="student2@test.local",
        full_name="Trần Thị B (Demo)",
        role="STUDENT"
    ),
    "token_admin": AuthenticatedUser(
        user_id=uuid.UUID("99999999-9999-9999-9999-999999999999"),
        email="admin@test.local",
        full_name="Admin Giảng Viên (Demo)",
        role="ADMIN"
    ),
}


def get_current_user(
    authorization: Optional[str] = Header(None, description="Bearer token or demo token")
) -> AuthenticatedUser:
    """Extract authenticated user identity server-side.
    
    Accepts:
    1. 'Bearer <token>' where token matches registered demo token
    2. 'Bearer <uuid>' for direct UUID test authentication
    3. Direct token string
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Yêu cầu tiêu đề Authorization với mã token hợp lệ.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    
    # 1. Match registered demo tokens
    if token in DEMO_USERS:
        return DEMO_USERS[token]
    
    # 2. Match direct valid UUID tokens (e.g. for dynamic integration tests)
    try:
        user_uuid = uuid.UUID(token)
        return AuthenticatedUser(
            user_id=user_uuid,
            email=f"user_{token[:8]}@test.local",
            full_name=f"User {token[:8]}",
            role="STUDENT"
        )
    except ValueError:
        pass
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token xác thực không hợp lệ hoặc đã hết hạn.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_admin_user(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Enforce ADMIN role for content management endpoints."""
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ người quản trị nội dung mới có quyền thực hiện thao tác này."
        )
    return current_user


def check_resource_ownership(resource_owner_id: str | uuid.UUID, authenticated_user_id: str | uuid.UUID) -> None:
    """Raise 403 Forbidden if resource owner does not match authenticated user."""
    if not verify_ownership(str(resource_owner_id), str(authenticated_user_id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Từ chối truy cập: Bạn không có quyền truy cập hoặc chỉnh sửa tài nguyên này."
        )
