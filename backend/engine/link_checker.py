"""Check whether a resource or JD URL still responds.

Only public http(s) hosts are contacted, so an administrator-entered URL cannot be used to reach
internal services. A site that blocks bots gives UNKNOWN rather than BROKEN: only a clear failure
hides a resource.
"""
from __future__ import annotations

import ipaddress
import socket
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

TIMEOUT_SECONDS = 8
MAX_REDIRECTS = 4
USER_AGENT = "Mozilla/5.0 (compatible; CareerAdapt-LinkCheck/4.0)"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def validate_public_url(url: str) -> Optional[str]:
    """Return an error message when the URL is not an http(s) URL on a public host."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "URL không hợp lệ."
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "URL phải bắt đầu bằng http:// hoặc https://."
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)}
    except (socket.gaierror, UnicodeError):
        return "Không phân giải được tên miền."
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            return "URL trỏ tới địa chỉ nội bộ, không được phép kiểm tra."
    return None


def check_url(url: str) -> dict:
    """Return {"link_status": OK|BROKEN|UNKNOWN, "http_status": int|None, "detail": str}."""
    if url.startswith("/"):
        return {"link_status": "OK", "http_status": None, "detail": "Tài liệu nội bộ của hệ thống."}
    opener = build_opener(_NoRedirect)
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        problem = validate_public_url(current)
        if problem:
            return {"link_status": "BROKEN", "http_status": None, "detail": problem}
        try:
            with opener.open(Request(current, headers={"User-Agent": USER_AGENT}), timeout=TIMEOUT_SECONDS) as response:
                return {"link_status": "OK", "http_status": response.status, "detail": "URL phản hồi."}
        except HTTPError as error:
            location = error.headers.get("Location") if error.code in {301, 302, 303, 307, 308} else None
            if location:
                current = urljoin(current, location)
                continue
            if error.code in {404, 410}:
                return {"link_status": "BROKEN", "http_status": error.code, "detail": "Trang không còn tồn tại."}
            return {"link_status": "UNKNOWN", "http_status": error.code, "detail": "Trang từ chối kiểm tra tự động; cần kiểm tra thủ công."}
        except (URLError, TimeoutError, OSError, ValueError):
            return {"link_status": "UNKNOWN", "http_status": None, "detail": "Không kết nối được; cần kiểm tra lại."}
    return {"link_status": "UNKNOWN", "http_status": None, "detail": "Chuyển hướng quá nhiều lần."}
