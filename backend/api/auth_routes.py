"""Browser account and session endpoints.

Errors return {"error": {"code", "message", "details"}} with a stable code so the
browser can show the message in the learner's language.
"""
from __future__ import annotations

import os
import re
import sqlite3
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

import logging

from fastapi import APIRouter, BackgroundTasks, File, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.accounts import (
    PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, PASSWORD_RULES, account_for_reset_token, RESET_TOKEN_SECONDS, SESSION_SECONDS, authenticate, begin_login_attempt, begin_registration_attempt,
    begin_reset_request, change_password, clear_login_failures, create_account, create_password_reset,
    create_session, get_account_profile, get_session, password_policy_failures, reset_password,
    revoke_session, update_account_profile,
)
from backend.accounts import avatar_version, delete_avatar, get_avatar, set_avatar
from backend.auth import session_cookie_name
from backend.avatar import MAX_UPLOAD_BYTES as AVATAR_MAX_BYTES, AvatarError, process_avatar
from backend import config
from backend.mailer import send_password_reset

logger = logging.getLogger("careeradapt.auth")

router = APIRouter(prefix="/auth", tags=["Accounts & Sessions"])
CSRF_COOKIE = "careeradapt_csrf"
EMAIL_PATTERN = r"[^\s@]+@[^\s@]+\.[^\s@]+"
PHONE_PATTERN = r"[0-9+()\-. ]{0,20}"


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class Registration(Credentials):
    full_name: str = Field(min_length=2, max_length=100)
    confirm_password: Optional[str] = Field(default=None, max_length=256)
    preferred_language: Literal["vi", "en"] = "vi"


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(default="", max_length=20)
    preferred_language: Literal["vi", "en"] = "vi"


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class ForgotPassword(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    preferred_language: Literal["vi", "en"] = "vi"


class PasswordReset(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


def _error(status_code: int, code: str, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message, "details": details}})


def _password_error(password: str, confirm: Optional[str], email: str = "", full_name: str = "") -> Optional[JSONResponse]:
    failures = password_policy_failures(password, email, full_name)
    if failures:
        return _error(422, "PASSWORD_POLICY", "Mật khẩu chưa đáp ứng đủ yêu cầu bảo mật.", {"failed_rules": failures})
    if confirm is not None and confirm != password:
        return _error(422, "PASSWORD_MISMATCH", "Mật khẩu nhập lại không khớp.")
    return None


def cookie_is_secure() -> bool:
    return os.getenv("CAREERADAPT_ENV", "development").lower() == "production"


def cookie_name(name: str) -> str:
    return f"__Host-{name}" if cookie_is_secure() else name


def set_session_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    secure = cookie_is_secure()
    response.set_cookie(
        key=session_cookie_name(), value=session_token, max_age=SESSION_SECONDS,
        httponly=True, secure=secure, samesite="strict", path="/",
    )
    response.set_cookie(
        key=cookie_name(CSRF_COOKIE), value=csrf_token, max_age=SESSION_SECONDS,
        httponly=False, secure=secure, samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"


def _iso(timestamp: Optional[int]) -> Optional[str]:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat() if timestamp else None


def _is_contributor(user_id: str) -> bool:
    from backend.contributions import is_contributor

    return is_contributor(user_id)


def safe_user(account: dict) -> dict:
    user = {"id": account["id"], "email": account["email"], "full_name": account["full_name"], "role": account["role"],
            # Changes whenever the picture changes, so the browser fetches the new one.
            "avatar_version": avatar_version(account["id"]),
            # Granted by an administrator; shows the "Đóng góp câu hỏi" page.
            "contributor": account["role"] == "admin" or _is_contributor(account["id"])}
    profile = get_account_profile(account["id"])
    if profile:
        user.update({
            "phone": profile.get("phone") or "",
            "preferred_language": profile.get("preferred_language") or "vi",
            "created_at": _iso(profile.get("created_at")),
            "last_login_at": _iso(profile.get("last_login_at")),
            "password_changed_at": _iso(profile.get("password_changed_at")),
        })
    return user


def _session_account(request: Request) -> Optional[dict]:
    token = request.cookies.get(session_cookie_name())
    return get_session(token) if token else None


def _unauthenticated() -> JSONResponse:
    return _error(401, "UNAUTHENTICATED", "Bạn cần đăng nhập để tiếp tục.")


@router.get("/csrf")
def issue_csrf_cookie(response: Response) -> dict:
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=cookie_name(CSRF_COOKIE), value=token, max_age=60 * 60,
        httponly=False, secure=cookie_is_secure(), samesite="strict", path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": token}


@router.get("/password-policy")
def password_policy() -> dict:
    return {"rules": [rule_id for rule_id, _ in PASSWORD_RULES], "min_length": PASSWORD_MIN_LENGTH, "max_length": PASSWORD_MAX_LENGTH}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: Registration, request: Request):
    """Create a learner account. No session is started: the learner signs in next."""
    ip = request.client.host if request.client else "unknown"
    if not begin_registration_attempt(ip):
        return _error(429, "RATE_LIMITED", "Đã vượt quá số lần tạo tài khoản cho phép. Vui lòng thử lại sau.")
    email = body.email.strip().casefold()
    if not re.fullmatch(EMAIL_PATTERN, email):
        return _error(422, "INVALID_EMAIL", "Vui lòng nhập địa chỉ email hợp lệ.")
    full_name = body.full_name.strip()
    if len(full_name) < 2:
        return _error(422, "INVALID_NAME", "Họ và tên cần có ít nhất 2 ký tự.")
    problem = _password_error(body.password, body.confirm_password, email, full_name)
    if problem:
        return problem
    try:
        account = create_account(email, full_name, body.password, role="student")
    except sqlite3.IntegrityError:
        return _error(400, "REGISTRATION_FAILED", "Không thể tạo tài khoản với thông tin này.")
    update_account_profile(account["id"], full_name, "", body.preferred_language)
    return {"user": {"email": account["email"], "full_name": account["full_name"]}, "next": "login"}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    email = body.email.strip().casefold()
    ip = request.client.host if request.client else "unknown"
    if not begin_login_attempt(email, ip):
        return _error(429, "LOGIN_RATE_LIMITED", "Quá nhiều lần đăng nhập thất bại. Vui lòng thử lại sau 15 phút.")
    account = authenticate(email, body.password)
    if account is None:
        return _error(401, "INVALID_CREDENTIALS", "Email hoặc mật khẩu không chính xác.")
    clear_login_failures(email, ip)
    token, csrf_token = create_session(account["id"])
    set_session_cookies(response, token, csrf_token)
    return {"user": safe_user(account)}


@router.get("/me")
def current_account(request: Request):
    account = _session_account(request)
    if account is None:
        return _unauthenticated()
    return {"user": safe_user(account)}


@router.patch("/me")
def update_current_account(body: ProfileUpdate, request: Request):
    account = _session_account(request)
    if account is None:
        return _unauthenticated()
    full_name = body.full_name.strip()
    if len(full_name) < 2:
        return _error(422, "INVALID_NAME", "Họ và tên cần có ít nhất 2 ký tự.")
    if not re.fullmatch(PHONE_PATTERN, body.phone.strip()):
        return _error(422, "INVALID_PHONE", "Số điện thoại chỉ gồm chữ số và các ký tự + ( ) - .")
    update_account_profile(account["id"], full_name, body.phone, body.preferred_language)
    return {"user": safe_user({**account, "full_name": full_name})}


@router.get("/me/avatar")
def read_avatar(request: Request):
    """The signed-in user's own picture. There is no route to read another account's picture."""
    account = _session_account(request)
    if account is None:
        return _unauthenticated()
    stored = get_avatar(account["id"])
    if stored is None:
        return _error(404, "NO_AVATAR", "Chưa có ảnh đại diện.")
    image, version = stored
    return Response(content=image, media_type="image/webp", headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": f'"{version}"'})


@router.put("/me/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    account = _session_account(request)
    if account is None:
        return _unauthenticated()
    data = await file.read(AVATAR_MAX_BYTES + 1)
    try:
        image = process_avatar(data)
    except AvatarError as error:
        return _error(413 if len(data) > AVATAR_MAX_BYTES else 422, "AVATAR_INVALID", str(error))
    set_avatar(account["id"], image)
    return {"user": safe_user(account)}


@router.delete("/me/avatar")
def remove_avatar(request: Request):
    account = _session_account(request)
    if account is None:
        return _unauthenticated()
    delete_avatar(account["id"])
    return {"user": safe_user(account)}


@router.post("/password/change")
def change_current_password(body: PasswordChange, request: Request):
    account = _session_account(request)
    if account is None:
        return _unauthenticated()
    problem = _password_error(body.new_password, body.confirm_password, account["email"], account.get("full_name", ""))
    if problem:
        return problem
    if body.new_password == body.current_password:
        return _error(422, "PASSWORD_UNCHANGED", "Mật khẩu mới phải khác mật khẩu hiện tại.")
    if not change_password(account["id"], body.current_password, body.new_password, request.cookies.get(session_cookie_name())):
        return _error(400, "WRONG_CURRENT_PASSWORD", "Mật khẩu hiện tại không đúng.")
    return {"ok": True, "other_sessions_revoked": True}


def public_base_url(request: Request) -> Optional[str]:
    """Where links in emails point. A forged Host header must never decide it in production."""
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    if os.getenv("CAREERADAPT_ENV", "development").lower() == "production":
        return None
    return str(request.base_url).rstrip("/")


def _deliver_reset(email: str, name: str, link: str, language: str) -> None:
    send_password_reset(email, name, link, language)


@router.post("/password/forgot")
def forgot_password(body: ForgotPassword, request: Request, background: BackgroundTasks):
    """Always answer the same way so the endpoint cannot be used to discover accounts.

    The email goes out after the response, so the answer time does not reveal whether the account
    exists. The link uses the configured public address, never the request's Host header.
    """
    ip = request.client.host if request.client else "unknown"
    if not begin_reset_request(ip):
        return _error(429, "RATE_LIMITED", "Bạn đã yêu cầu quá nhiều lần. Vui lòng thử lại sau.")
    email = body.email.strip().casefold()
    if re.fullmatch(EMAIL_PATTERN, email):
        issued = create_password_reset(email)
        if issued:
            token, account = issued
            # The token travels in the URL fragment, so it is never sent to the server in logs or referrers.
            base = public_base_url(request)
            if base is None:
                logger.error("Password reset requested but CAREERADAPT_PUBLIC_URL is not set in production; no email was sent.")
            else:
                link = f"{base}/login#reset={token}"
                background.add_task(_deliver_reset, account["email"], account["full_name"], link, account.get("preferred_language") or body.preferred_language)
    return {"ok": True, "expires_in_minutes": RESET_TOKEN_SECONDS // 60}


@router.post("/password/reset")
def reset_forgotten_password(body: PasswordReset):
    owner = account_for_reset_token(body.token) or {}
    problem = _password_error(body.new_password, body.confirm_password, owner.get("email", ""), owner.get("full_name", ""))
    if problem:
        return problem
    if not reset_password(body.token, body.new_password):
        return _error(400, "RESET_TOKEN_INVALID", "Liên kết đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.")
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(session_cookie_name())
    if token:
        revoke_session(token)
    secure = cookie_is_secure()
    response.delete_cookie(key=session_cookie_name(), path="/", secure=secure, httponly=True, samesite="strict")
    response.delete_cookie(key=cookie_name(CSRF_COOKIE), path="/", secure=secure, httponly=False, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
