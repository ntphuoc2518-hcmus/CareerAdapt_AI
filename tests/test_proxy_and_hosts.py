"""Audit B-06 / B-07 on a real uvicorn server (temporary database): the Host allow-list and trusted proxies.

The settings existed since 5.18.0 but had no test. The server runs with the same uvicorn options as run.py.
"""
from __future__ import annotations

import http.client
import json
import subprocess
import time
import urllib.error
import urllib.request

import pytest

from test_multiprocess import PYTHON, ROOT, environment, free_ports


@pytest.fixture
def server(tmp_path):
    env = environment(tmp_path)
    env["CAREERADAPT_ALLOWED_HOSTS"] = "careeradapt.test,127.0.0.1"
    port = free_ports(1)[0]
    log = open(tmp_path / "server.log", "wb")
    process = subprocess.Popen([PYTHON, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
                                "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(240):
            if process.poll() is not None:
                raise RuntimeError("server stopped: " + (tmp_path / "server.log").read_text(encoding="utf-8", errors="replace")[-2000:])
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2):
                    break
            except (OSError, ValueError, http.client.HTTPException):
                time.sleep(0.25)
        yield port
    finally:
        process.terminate()
        process.wait(timeout=30)
        log.close()


# What the login page sends: same origin and the double-submit CSRF pair.
BROWSER = {"Origin": "http://careeradapt.test", "Cookie": "careeradapt_csrf=t0k3n", "X-CSRF-Token": "t0k3n"}


def send(port: int, method: str, path: str, headers: dict, body=None) -> int:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method, headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_a_host_outside_the_allow_list_is_refused(server):
    assert send(server, "GET", "/health", {"Host": "careeradapt.test"}) == 200
    assert send(server, "GET", "/health", {"Host": "evil.example"}) == 400


def test_login_limits_count_the_client_behind_a_trusted_proxy(server):
    """30 failed logins from one forwarded address lock that address only, not every client of the proxy."""
    def login(ip: str, index: int) -> int:
        return send(server, "POST", "/api/v1/auth/login", {"Host": "careeradapt.test", "X-Forwarded-For": ip, **BROWSER}, {"email": f"nobody{index}@example.com", "password": "Sai-mat-khau-1"})

    statuses = [login("203.0.113.7", index) for index in range(30)]
    assert all(code == 401 for code in statuses), statuses
    assert login("203.0.113.7", 99) == 429
    assert login("198.51.100.4", 100) == 401
