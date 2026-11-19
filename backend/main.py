"""CareerAdapt AI v5.0 - Main FastAPI Application Server.

Orchestrates:
- REST API Routers (F01 - F10, 8 Reference APIs, Admin CRUD)
- CSRF Protection & Standardized Error Handling
- Static Frontend Serving & Single-Command Launcher
"""
from __future__ import annotations
import json
import os
import secrets
import sys
from pathlib import Path
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError, HTTPException
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from urllib.parse import urlsplit

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend import config, i18n
from backend.config import APP_NAME, APP_VERSION
from backend.accounts import get_session
from backend.auth import resolve_user, session_cookie_name, legacy_demo_auth_enabled
from backend.store import UserBusy, store
from starlette.concurrency import run_in_threadpool
from backend.api.reference_apis import router as reference_apis_router
from backend.api.admin_crud import router as admin_router
from backend.api.auth_routes import router as auth_router, CSRF_COOKIE, cookie_name
from backend.api.test_center import router as test_center_router
from backend.api.skill_report import router as skill_report_router
from backend.api.jds import router as jd_router, admin_router as jd_admin_router
from backend.api.resources import router as resource_router, admin_router as resource_admin_router
from backend.api.learning_cycle import router as learning_cycle_router
from backend.api.learning_tasks import router as learning_tasks_router
from backend.api.journey import router as journey_router
from backend.api.career_process import router as career_process_router
from backend.api.assistant import i18n_router, router as assistant_router
from backend.api.contributions import router as contributions_router
from backend.background import lifespan

app = FastAPI(
    lifespan=lifespan,
    title=f"{APP_NAME} - Backend API",
    description="Hệ thống phát triển năng lực Data Analyst bằng đánh giá có bằng chứng, mục tiêu theo JD và lộ trình học cá nhân hóa (V5.0)",
    version=APP_VERSION,
    docs_url="/docs" if os.getenv("CAREERADAPT_ENV", "development").lower() != "production" else None,
    redoc_url="/redoc" if os.getenv("CAREERADAPT_ENV", "development").lower() != "production" else None,
    openapi_url="/openapi.json" if os.getenv("CAREERADAPT_ENV", "development").lower() != "production" else None
)

if config.ALLOWED_HOSTS:
    # Production behind a domain: requests for any other Host are refused before they reach a route.
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.ALLOWED_HOSTS)


API_PREFIXES = ("/auth", "/careers", "/me", "/submissions", "/assessments", "/roadmaps", "/activities", "/admin", "/jds", "/tasks", "/learning-resources", "/micro-tests")
# The assistant waits on the AI service for seconds and only reads learner data, so it refreshes without the lock.
LOCK_FREE_PREFIXES = ("/api/v1/assistant/",)


def is_api_path(path: str) -> bool:
    return path.startswith("/api/") or path.startswith(API_PREFIXES)


def _refresh(user) -> None:
    store.sync_content()
    store.sync_user(user.user_id)
    if user.role == "admin":
        # Administrators read across learners (review queue, results), so they see every process's changes.
        store.sync_all()


# Defined before security_middleware, so it runs inside it: a request refused for CSRF never takes a lock.
@app.middleware("http")
async def learner_sync_middleware(request: Request, call_next):
    """Several server processes (5.34): hold the learner's lock for the request and start from their latest data."""
    path = request.url.path
    if not is_api_path(path):
        return await call_next(request)
    user = await run_in_threadpool(resolve_user, request)
    if user is None:
        return await call_next(request)
    request.state.careeradapt_user = user
    if path.startswith(LOCK_FREE_PREFIXES):
        await run_in_threadpool(_refresh, user)
        return await call_next(request)
    try:
        owner = await run_in_threadpool(store.acquire_user, user.user_id)
    except UserBusy:
        busy = JSONResponse(status_code=503, headers={"Retry-After": "3"}, content={"error": {"code": "LEARNER_BUSY", "message": "Dữ liệu của bạn đang được cập nhật ở một yêu cầu khác. Hãy thử lại sau vài giây.", "details": None}})
        return _apply_security_headers(busy, api_response=True)
    token = store.mark_held(user.user_id)
    try:
        await run_in_threadpool(_refresh, user)
        return await call_next(request)
    finally:
        store.unmark_held(token)
        await run_in_threadpool(store.release_user, user.user_id, owner)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Same-origin browser API, double-submit CSRF validation and baseline headers."""
    method = request.method.upper()
    path = request.url.path
    i18n.set_language(request.headers.get("x-language"))
    api_path = is_api_path(path)
    authorization = request.headers.get("authorization", "")
    legacy_demo_request = legacy_demo_auth_enabled() and authorization.lower().startswith("bearer ")
    if api_path and method in {"POST", "PUT", "PATCH", "DELETE"} and not legacy_demo_request:
        origin = request.headers.get("origin")
        expected_origin = f"{request.url.scheme}://{request.url.netloc}"
        if not origin or urlsplit(origin).scheme + "://" + urlsplit(origin).netloc != expected_origin:
            blocked = JSONResponse(status_code=403, content={"error": {"code": "CSRF_ORIGIN_REJECTED", "message": "Yêu cầu phải đến từ trang CareerAdapt AI.", "details": None}})
            return _apply_security_headers(blocked, api_response=True)
        csrf_cookie = request.cookies.get(cookie_name(CSRF_COOKIE), "")
        csrf_header = request.headers.get("x-csrf-token", "")
        if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
            blocked = JSONResponse(status_code=403, content={"error": {"code": "CSRF_TOKEN_REJECTED", "message": "Phiên bảo mật đã hết hạn. Hãy tải lại trang và thử lại.", "details": None}})
            return _apply_security_headers(blocked, api_response=True)
        session_token = request.cookies.get(session_cookie_name())
        # Bind CSRF to live sessions only. An expired or unknown session cookie grants nothing,
        # and rejecting it here would lock the user out of the login form that replaces it.
        # Logout is exempt so a stale security cookie can never trap a user in a session.
        is_logout = path.rstrip("/").endswith("/auth/logout")
        if not is_logout and session_token and get_session(session_token) is not None and get_session(session_token, csrf_header) is None:
            blocked = JSONResponse(status_code=403, content={"error": {"code": "CSRF_SESSION_REJECTED", "message": "Phiên bảo mật không hợp lệ. Hãy đăng nhập lại.", "details": None}})
            return _apply_security_headers(blocked, api_response=True)
    response = await call_next(request)
    if i18n.should_translate(path) and response.headers.get("content-type", "").startswith("application/json"):
        response = await _translated(response)
    # Modules import each other without a version, so browsers must ask before reusing a cached copy.
    if path.startswith(("/js/", "/css/", "/img/")):
        response.headers["Cache-Control"] = "no-cache"
    return _apply_security_headers(response, api_response=api_path)


async def _translated(response):
    body = b"".join([chunk async for chunk in response.body_iterator])
    headers = {key: value for key, value in response.headers.items() if key.lower() != "content-length"}
    return JSONResponse(content=i18n.localize(json.loads(body)), status_code=response.status_code, headers=headers)


def _apply_security_headers(response, api_response: bool = False):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(self), geolocation=()")
    if api_response:
        response.headers["Cache-Control"] = "no-store"
    if os.getenv("CAREERADAPT_ENV", "development").lower() == "production":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


# 2. Standardized Error Handling
# Registered for the Starlette base class, so errors raised below FastAPI (an oversized form field, an unknown
# path) use the same envelope as the rest of the API instead of a bare {"detail": ...} (audit 2026-11-15).
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    message = exc.detail
    if exc.status_code == 400 and isinstance(message, str) and "exceeded maximum size" in message:
        message = "Nội dung gửi lên quá lớn. Hãy rút gọn nội dung hoặc chọn tệp nhỏ hơn."
    return JSONResponse(
        status_code=exc.status_code, headers=getattr(exc, "headers", None),
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": message,
                "details": None
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Dữ liệu đầu vào không hợp lệ theo quy định schema.",
                "details": exc.errors()
            }
        },
    )


# 3. Mount API Routers
API_V1_PREFIX = "/api/v1"
app.include_router(reference_apis_router, prefix=API_V1_PREFIX)
app.include_router(admin_router, prefix=API_V1_PREFIX)
app.include_router(auth_router, prefix=API_V1_PREFIX)
app.include_router(test_center_router, prefix=API_V1_PREFIX)
app.include_router(skill_report_router, prefix=API_V1_PREFIX)
app.include_router(career_process_router, prefix=API_V1_PREFIX)
app.include_router(assistant_router, prefix=API_V1_PREFIX)
app.include_router(i18n_router, prefix=API_V1_PREFIX)
app.include_router(contributions_router, prefix=API_V1_PREFIX)
for router_v4 in (jd_router, jd_admin_router, resource_router, resource_admin_router, learning_cycle_router, learning_tasks_router, journey_router):
    app.include_router(router_v4, prefix=API_V1_PREFIX)
    # The specification's reference paths (/jds/import, /me/reminders, ...) also work at root level.
    app.include_router(router_v4, include_in_schema=False)

# Also mount at root level for strict RFC endpoint compatibility (/careers, /me/profile, etc.)
# They stay out of the API document so each operation is listed once, under /api/v1.
app.include_router(reference_apis_router, include_in_schema=False)
app.include_router(admin_router, include_in_schema=False)
app.include_router(auth_router, include_in_schema=False)


# 4. Root & Health Check Endpoints
@app.get("/health", tags=["Health"])
def health_check():
    """Service health status check."""
    return {
        "status": "healthy",
        "service": "CareerAdapt AI Backend",
        "version": APP_VERSION
    }


# 5. Static Files & Frontend SPA Serving
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    css_dir = FRONTEND_DIR / "css"
    js_dir = FRONTEND_DIR / "js"
    if css_dir.exists():
        app.mount("/css", StaticFiles(directory=str(css_dir)), name="css")
    if js_dir.exists():
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")
    img_dir = FRONTEND_DIR / "img"
    if img_dir.exists():
        app.mount("/img", StaticFiles(directory=str(img_dir)), name="img")
    guides_dir = FRONTEND_DIR / "guides"
    if guides_dir.exists():
        app.mount("/guides", StaticFiles(directory=str(guides_dir)), name="guides")

    APP_CSP = "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; img-src 'self' data:; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'"
    NO_CACHE_HEADERS = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }

    @app.get("/app", tags=["Frontend SPA"])
    def serve_frontend_app(request: Request):
        if not _authenticated(request):
            redirect = RedirectResponse("/login", status_code=303)
            redirect.headers.update(NO_CACHE_HEADERS)
            return redirect
        page = FileResponse(str(FRONTEND_DIR / "index.html"), headers=NO_CACHE_HEADERS)
        page.headers["Content-Security-Policy"] = APP_CSP
        return page

    @app.get("/index.html", tags=["Frontend SPA"])
    def serve_frontend_index(request: Request):
        if not _authenticated(request):
            redirect = RedirectResponse("/login", status_code=303)
            redirect.headers.update(NO_CACHE_HEADERS)
            return redirect
        page = FileResponse(str(FRONTEND_DIR / "index.html"), headers=NO_CACHE_HEADERS)
        page.headers["Content-Security-Policy"] = APP_CSP
        return page

    @app.get("/", tags=["Frontend SPA"])
    def serve_root(request: Request):
        redirect = RedirectResponse("/app" if _authenticated(request) else "/gioi-thieu", status_code=303)
        redirect.headers.update(NO_CACHE_HEADERS)
        return redirect

    @app.get("/gioi-thieu", tags=["Frontend SPA"])
    def serve_landing():
        """Public introduction: static text only, no account data and no API calls."""
        page = FileResponse(str(FRONTEND_DIR / "landing.html"), headers=NO_CACHE_HEADERS)
        page.headers["Content-Security-Policy"] = "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'"
        return page

    @app.get("/login", tags=["Frontend SPA"])
    def serve_login(request: Request):
        if _authenticated(request):
            redirect = RedirectResponse("/app", status_code=303)
            redirect.headers.update(NO_CACHE_HEADERS)
            return redirect
        page = FileResponse(str(FRONTEND_DIR / "login.html"), headers=NO_CACHE_HEADERS)
        page.headers["Content-Security-Policy"] = "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'"
        return page


@app.get("/api", tags=["API Root"])
def api_root_info():
    """API info pointing to interactive Swagger documentation."""
    return {
        "message": f"Chào mừng đến với API {APP_NAME} (Phiên bản {APP_VERSION})",
        "docs_url": app.docs_url,
        "openapi_url": app.openapi_url
    }


def _authenticated(request: Request) -> bool:
    token = request.cookies.get(session_cookie_name())
    return bool(token and get_session(token))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
