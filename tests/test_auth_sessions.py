"""Accounts: registration, password policy, profile, password change/reset and CSRF session binding."""
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.accounts import password_policy_failures
from backend.api import auth_routes
from backend.auth import session_cookie_name
from backend.main import app

ORIGIN = {"Origin": "http://testserver"}
STRONG = "Strong-Pass-123"


@pytest.fixture(autouse=True)
def reset_throttles():
    # Every TestClient shares one address, so per-IP limits would trip across tests.
    from contextlib import closing
    from backend.accounts import _connect
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM registration_attempts")
        conn.execute("DELETE FROM login_attempts")


def _email(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.test"


def _headers(client):
    client.get("/api/v1/auth/csrf")
    return {**ORIGIN, "X-CSRF-Token": client.cookies.get("careeradapt_csrf")}


def _register(client, email, password=STRONG, confirm=None, **extra):
    body = {"email": email, "password": password, "full_name": "Kiểm Thử Phiên",
            "confirm_password": password if confirm is None else confirm, **extra}
    return client.post("/api/v1/auth/register", headers=_headers(client), json=body)


def _login(client, email, password=STRONG):
    return client.post("/api/v1/auth/login", headers=_headers(client), json={"email": email, "password": password})


def _signed_in(email=None, password=STRONG):
    client = TestClient(app)
    email = email or _email("user")
    assert _register(client, email, password).status_code == 201
    assert _login(client, email, password).status_code == 200
    return client, email


def _write_headers(client):
    # After login the CSRF cookie is the one bound to the session.
    return {**ORIGIN, "X-CSRF-Token": client.cookies.get("careeradapt_csrf")}


# --- Password policy ---------------------------------------------------------

# 5.26 (team decision): at least 8 characters, one uppercase letter and one special character.
@pytest.mark.parametrize("password,missing", [
    ("Sh0rt#A", {"length"}),
    ("", {"length", "upper", "special"}),
    ("x" * 129 + "A!", {"length"}),
    ("alllowercase-123", {"upper"}),
    ("NoSpecial12345", {"special"}),
    ("nospecialnoupper", {"upper", "special"}),
    ("Spaces Only Here", {"special"}),
    ("Mật-Khẩu-Việt", set()),
    ("Password#1", set()),
    ("Ánh@sáng", set()),
])
def test_password_policy_rules(password, missing):
    assert set(password_policy_failures(password)) == missing


def test_the_policy_endpoint_lists_the_rules():
    policy = TestClient(app).get("/api/v1/auth/password-policy").json()
    assert policy["rules"] == ["length", "upper", "special"] and policy["min_length"] == 8


# --- Registration --------------------------------------------------------------

def test_register_does_not_sign_in_and_requires_login():
    client = TestClient(app)
    email = _email("reg")
    resp = _register(client, email)
    assert resp.status_code == 201 and resp.json()["next"] == "login"
    assert not client.cookies.get(session_cookie_name())
    assert client.get("/api/v1/auth/me").status_code == 401
    assert _login(client, email).status_code == 200
    assert client.get("/api/v1/auth/me").json()["user"]["email"] == email


def test_register_rejects_weak_password_with_failed_rules():
    resp = _register(TestClient(app), _email("weak"), "weakpassword")
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "PASSWORD_POLICY"
    assert set(error["details"]["failed_rules"]) == {"upper", "special"}
    assert _register(TestClient(app), _email("regok"), "Eight#chr").status_code == 201


def test_register_rejects_mismatched_confirmation():
    resp = _register(TestClient(app), _email("mismatch"), STRONG, confirm=STRONG + "x")
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "PASSWORD_MISMATCH"


def test_register_saves_language_choice():
    client = TestClient(app)
    email = _email("lang")
    _register(client, email, preferred_language="en")
    _login(client, email)
    assert client.get("/api/v1/auth/me").json()["user"]["preferred_language"] == "en"


# --- Profile ---------------------------------------------------------------------

def test_profile_update_and_details():
    client, email = _signed_in()
    me = client.get("/api/v1/auth/me").json()["user"]
    assert me["created_at"] and me["last_login_at"] and me["password_changed_at"]
    resp = client.patch("/api/v1/auth/me", headers=_write_headers(client),
                        json={"full_name": "Trần Minh Anh", "phone": "+84 912 345 678", "preferred_language": "en"})
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert (user["full_name"], user["phone"], user["preferred_language"], user["email"]) == ("Trần Minh Anh", "+84 912 345 678", "en", email)
    bad = client.patch("/api/v1/auth/me", headers=_write_headers(client),
                       json={"full_name": "Trần Minh Anh", "phone": "call me", "preferred_language": "en"})
    assert bad.json()["error"]["code"] == "INVALID_PHONE"
    assert client.patch("/api/v1/auth/me", headers=_write_headers(client),
                        json={"full_name": "X Y", "preferred_language": "fr"}).status_code == 422


def test_profile_requires_session():
    client = TestClient(app)
    resp = client.patch("/api/v1/auth/me", headers=_headers(client), json={"full_name": "Ai Đó", "preferred_language": "vi"})
    assert resp.status_code == 401


# --- Password change ----------------------------------------------------------------

def test_change_password_revokes_other_sessions():
    client, email = _signed_in()
    other = TestClient(app)
    assert _login(other, email).status_code == 200

    new_password = "Brand-New-Pass-456"
    wrong = client.post("/api/v1/auth/password/change", headers=_write_headers(client),
                        json={"current_password": "Wrong-Pass-000", "new_password": new_password, "confirm_password": new_password})
    assert wrong.json()["error"]["code"] == "WRONG_CURRENT_PASSWORD"

    ok = client.post("/api/v1/auth/password/change", headers=_write_headers(client),
                     json={"current_password": STRONG, "new_password": new_password, "confirm_password": new_password})
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200   # this session stays
    assert other.get("/api/v1/auth/me").status_code == 401    # other device signed out
    assert _login(TestClient(app), email, STRONG).status_code == 401
    assert _login(TestClient(app), email, new_password).status_code == 200


# --- Forgot / reset ---------------------------------------------------------------

@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(auth_routes, "send_password_reset", lambda email, name, link, language="vi": sent.append({"email": email, "link": link, "language": language}))
    return sent


def test_forgot_password_is_generic_for_unknown_email(outbox):
    client = TestClient(app)
    resp = client.post("/api/v1/auth/password/forgot", headers=_headers(client), json={"email": _email("nobody")})
    assert resp.status_code == 200 and resp.json()["ok"] is True
    assert outbox == []


def test_reset_password_flow_single_use_and_revokes_sessions(outbox):
    client, email = _signed_in()
    anon = TestClient(app)
    assert anon.post("/api/v1/auth/password/forgot", headers=_headers(anon), json={"email": email.upper()}).status_code == 200
    assert len(outbox) == 1 and outbox[0]["email"] == email
    link = outbox[0]["link"]
    assert "/login#reset=" in link  # token in the fragment, never sent back to the server
    token = link.split("#reset=")[1]

    weak = anon.post("/api/v1/auth/password/reset", headers=_headers(anon), json={"token": token, "new_password": "weak", "confirm_password": "weak"})
    assert weak.json()["error"]["code"] == "PASSWORD_POLICY"

    new_password = "Reset-Pass-789!"
    body = {"token": token, "new_password": new_password, "confirm_password": new_password}
    assert anon.post("/api/v1/auth/password/reset", headers=_headers(anon), json=body).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401  # existing sessions revoked
    assert _login(TestClient(app), email, new_password).status_code == 200

    reused = anon.post("/api/v1/auth/password/reset", headers=_headers(anon), json=body)
    assert reused.json()["error"]["code"] == "RESET_TOKEN_INVALID"


def test_new_reset_request_invalidates_previous_link(outbox):
    _, email = _signed_in()
    anon = TestClient(app)
    for _ in range(2):
        anon.post("/api/v1/auth/password/forgot", headers=_headers(anon), json={"email": email})
    first, second = (item["link"].split("#reset=")[1] for item in outbox)
    pw = "Another-Pass-321!"
    assert anon.post("/api/v1/auth/password/reset", headers=_headers(anon),
                     json={"token": first, "new_password": pw, "confirm_password": pw}).json()["error"]["code"] == "RESET_TOKEN_INVALID"
    assert anon.post("/api/v1/auth/password/reset", headers=_headers(anon),
                     json={"token": second, "new_password": pw, "confirm_password": pw}).status_code == 200


# --- CSRF session binding -----------------------------------------------------------

def test_login_succeeds_with_stale_session_cookie():
    email = _email("stale")
    assert _register(TestClient(app), email).status_code == 201
    fresh = TestClient(app)
    # e.g. a cookie from another local server or an expired session
    fresh.cookies.set(session_cookie_name(), "no-such-session")
    assert _login(fresh, email).status_code == 200


def test_live_session_still_rejects_mismatched_csrf():
    client, _ = _signed_in()
    assert client.cookies.get(session_cookie_name())
    # Double-submit pair matches, but it is not the token bound to this session.
    client.cookies.set("careeradapt_csrf", "forged-token")
    resp = client.patch("/api/v1/auth/me", headers={**ORIGIN, "X-CSRF-Token": "forged-token"},
                        json={"full_name": "Kẻ Giả Mạo", "preferred_language": "vi"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_SESSION_REJECTED"


def test_logout_works_even_with_stale_csrf_cookie():
    client, _ = _signed_in()
    # e.g. another local server on a different port replaced the shared CSRF cookie
    client.cookies.set("careeradapt_csrf", "replaced-token")
    resp = client.post("/api/v1/auth/logout", headers={**ORIGIN, "X-CSRF-Token": "replaced-token"})
    assert resp.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
