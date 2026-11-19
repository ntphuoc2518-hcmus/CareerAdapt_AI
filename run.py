"""CareerAdapt AI - Unified System Launcher & Server Orchestrator.

Starts the FastAPI Backend and launches the interactive Frontend in the default browser.
Author: Principal Software Architect & Senior AI Engineer
Subject: Computational Thinking (Tư Duy Tính Toán - HCMUS)
"""
import sys
import os
import time
import webbrowser
import threading
from urllib.error import URLError
from urllib.request import urlopen

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import uvicorn

from backend import config  # loads .env, so HOST and PORT below can come from it

# HOST and PORT come from .env or the environment (see .env.example); the defaults keep the server on this computer.
HOST = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
PORT = int(os.getenv("PORT", "8000"))
# Listening on every interface is still reached locally through 127.0.0.1.
LOCAL_HOST = "127.0.0.1" if HOST in {"0.0.0.0", "::"} else HOST
BASE_URL = f"http://{LOCAL_HOST}:{PORT}"


def open_browser_delayed():
    """Open the UI only after FastAPI is responding to health checks."""
    app_url = f"{BASE_URL}/login"
    health_url = f"{BASE_URL}/health"
    for _ in range(60):
        try:
            with urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    break
        except (OSError, URLError):
            time.sleep(0.5)
    else:
        print("\n[WARN] May chu chua san sang sau 30 giay.")
        print(f"       Hay mo thu cong: {app_url}\n")
        return

    print(f"\n[OK] Đang mở trang đăng nhập CareerAdapt AI:")
    print(f"     -> {app_url}\n")
    if not webbrowser.open(app_url):
        print("[WARN] Khong mo duoc trinh duyet mac dinh. Hay sao chep URL o tren.\n")


def main():
    print("=" * 80)
    print("   CAREERADAPT AI - PHÁT TRIỂN NĂNG LỰC DATA ANALYST CÓ BẰNG CHỨNG")
    print("=" * 80)
    print(f"\n[INFO] Đang khởi động máy chủ trên {BASE_URL} ...")
    print(f"       - Trang đăng nhập:  {BASE_URL}/login")
    print(f"       - Tài liệu API:     {BASE_URL}/docs")
    print(f"       - Kiểm tra máy chủ: {BASE_URL}/health")
    print("=" * 80)

    # Launch browser in a background thread (CAREERADAPT_OPEN_BROWSER=false skips it, e.g. on a server).
    if os.getenv("CAREERADAPT_OPEN_BROWSER", "true").strip().lower() not in {"0", "false", "no"}:
        threading.Thread(target=open_browser_delayed, daemon=True).start()

    # Run uvicorn server
    # Only the listed proxies may set X-Forwarded-For; login limits then count the real client address.
    # CAREERADAPT_WORKERS > 1 starts that many server processes on the same database (5.34). They share
    # learner data through SQLite: each request takes the learner's lock and reloads what another process changed.
    workers = max(1, int(os.getenv("CAREERADAPT_WORKERS", "1")))
    if workers > 1:
        print(f"[INFO] Chạy {workers} tiến trình máy chủ dùng chung cơ sở dữ liệu.")
    uvicorn.run("backend.main:app", host=HOST, port=PORT, log_level="info", proxy_headers=True, forwarded_allow_ips=config.TRUSTED_PROXIES, workers=workers)


if __name__ == "__main__":
    main()
