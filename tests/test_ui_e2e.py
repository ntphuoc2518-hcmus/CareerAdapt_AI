"""End-to-end interface tests in a real browser (5.34).

A real server is started on a free port with databases in a temporary folder, and Playwright drives the
installed Microsoft Edge (or Chrome) in headless mode. Nothing in data/ is opened for writing. The tests are
skipped when Playwright or a browser is missing, so the rest of the suite runs anywhere.

Run only these:  python -m pytest tests/test_ui_e2e.py -q
"""
import http.client
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed (pip install -r requirements-dev.txt)")

expect = playwright_api.expect
ROOT = Path(__file__).resolve().parents[1]
NAME, EMAIL, PASSWORD = "Học Viên Kiểm Thử", "ui.test@example.com", "Kiem-Thu#2026"
PAGES = ["/", "/process", "/plan", "/resources", "/tests", "/profile", "/plan/da/progress", "/report"]
ADMIN_NAME, ADMIN_EMAIL, ADMIN_PASSWORD = "Quản Trị Kiểm Thử", "admin.ui.test@example.com", "Quan-Tri#2026"
SERVER_DIRS: dict[str, Path] = {}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    folder = tmp_path_factory.mktemp("ui-server")
    SERVER_DIRS["folder"] = folder
    env = {key: value for key, value in os.environ.items() if not key.startswith("CAREERADAPT_")}
    env.update({
        "CAREERADAPT_DB": str(folder / "careeradapt.sqlite3"), "CAREERADAPT_ACCOUNTS_DB": str(folder / "accounts.sqlite3"),
        "CAREERADAPT_STATE_PATH": str(folder / "none.json"), "CAREERADAPT_QUESTION_BANK_OVERRIDES_PATH": str(folder / "bank.json"),
        "CAREERADAPT_ENV": "development", "CAREERADAPT_AUTO_LINK_CHECK": "false", "LLM_PROVIDER": "mock", "PYTHONIOENCODING": "utf-8",
    })
    port = free_port()
    # Server output goes to a file: an unread pipe fills up and freezes the server.
    log_path = folder / "server.log"
    log = open(log_path, "wb")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                               cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(240):
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2):
                break
        except (OSError, ValueError, http.client.HTTPException):
            if process.poll() is not None:
                raise RuntimeError(log_path.read_text(encoding="utf-8", errors="replace")[-2000:])
            time.sleep(0.25)
    else:
        process.terminate()
        raise RuntimeError("server did not start: " + log_path.read_text(encoding="utf-8", errors="replace")[-2000:])
    yield base
    process.terminate()
    process.wait(timeout=30)
    log.close()


@pytest.fixture(scope="module")
def browser():
    with playwright_api.sync_playwright() as playwright:
        launched = None
        for channel in ("msedge", "chrome", None):
            try:
                launched = playwright.chromium.launch(channel=channel, headless=True) if channel else playwright.chromium.launch(headless=True)
                break
            except Exception:
                continue
        if launched is None:
            pytest.skip("No Chromium-based browser is available for Playwright")
        yield launched
        launched.close()


class Watched:
    """A page plus every script error and failed API call seen while it was open."""

    def __init__(self, page, base):
        self.page, self.base, self.errors = page, base, []
        page.on("pageerror", lambda error: self.errors.append(f"pageerror: {error}"))
        page.on("console", lambda message: self.errors.append(f"console: {message.text}") if message.type == "error" else None)
        page.on("response", lambda response: self.errors.append(f"{response.status} {response.url}") if "/api/" in response.url and response.status >= 500 else None)

    def open(self, path):
        self.page.goto(self.base + path)
        return self.page


@pytest.fixture(scope="module")
def signed_in_state(server, browser, tmp_path_factory):
    """Register and sign in through the real forms once; later tests reuse the session."""
    context = browser.new_context(locale="vi-VN")
    watched = Watched(context.new_page(), server)
    page = watched.open("/login")
    page.click("#tab-register")
    page.fill("#register-name", NAME)
    page.fill("#register-email", EMAIL)
    page.fill("#register-password", PASSWORD)
    page.fill("#register-confirm", PASSWORD)
    page.click("#register-form button[type=submit]")
    page.wait_for_selector("#login-form:not([hidden])")
    assert page.input_value("#login-email") == EMAIL
    page.fill("#login-password", PASSWORD)
    page.click("#login-form button[type=submit]")
    page.wait_for_url("**/app**")
    expect(page.locator("#page-title")).to_have_text("Bảng điều khiển")
    assert watched.errors == []
    state = tmp_path_factory.mktemp("ui-state") / "state.json"
    context.storage_state(path=str(state))
    context.close()
    return str(state)


@pytest.fixture
def app(server, browser, signed_in_state):
    context = browser.new_context(storage_state=signed_in_state, locale="vi-VN", viewport={"width": 1366, "height": 900})
    watched = Watched(context.new_page(), server)
    yield watched
    context.close()


def wait_ready(page):
    # Locator checks, not page-side script: the app's Content Security Policy forbids evaluating strings.
    expect(page.locator("#page-title")).not_to_have_text("CareerAdapt AI")
    expect(page.locator("#view .loading, #view .skeleton")).to_have_count(0)


# --- Accounts ---

def test_a_wrong_password_is_refused_on_the_sign_in_form(server, browser, signed_in_state):
    context = browser.new_context()
    page = Watched(context.new_page(), server).open("/login")
    page.fill("#login-email", EMAIL)
    page.fill("#login-password", "Sai-Mat-Khau#1")
    page.click("#login-form button[type=submit]")
    page.wait_for_selector("#login-message:not([hidden])")
    assert "/login" in page.url
    context.close()


def test_the_password_checklist_blocks_a_weak_password(server, browser):
    context = browser.new_context()
    page = Watched(context.new_page(), server).open("/login")
    page.click("#tab-register")
    page.fill("#register-password", "yeu")
    assert page.is_disabled("#register-form button[type=submit]")
    context.close()


def test_signing_out_returns_to_the_sign_in_page(server, browser, signed_in_state):
    # Its own session: signing out revokes the session it uses, so it must not be the shared one.
    context = browser.new_context()
    watched = Watched(context.new_page(), server)
    page = watched.open("/login")
    page.fill("#login-email", EMAIL)
    page.fill("#login-password", PASSWORD)
    page.click("#login-form button[type=submit]")
    page.wait_for_url("**/app**")
    wait_ready(page)
    page.click("#logout")
    page.wait_for_url("**/login**")
    # The session is gone on the server too: the app sends the visitor back to sign in.
    watched.open("/app")
    page.wait_for_url("**/login**")
    assert watched.errors == []
    context.close()


def test_signing_in_again_returns_to_the_page_the_learner_was_on(server, browser, signed_in_state):
    # Audit 2026-11-18: a link opened while signed out, or a session that ended mid-task, used to land on the
    # dashboard after signing in. The page is kept as an in-app fragment only.
    context = browser.new_context(locale="vi-VN")
    page = Watched(context.new_page(), server).open("/app#/resources")
    # The sign-in page keeps the fragment (wait on the form: wait_for_url hangs on a URL with a fragment).
    expect(page.locator("#login-form")).to_be_visible()
    assert page.url.endswith("/login#/resources")

    def sign_in():
        page.fill("#login-email", EMAIL)
        page.fill("#login-password", PASSWORD)
        page.click("#login-form button[type=submit]")
        expect(page.locator("#view")).to_be_visible()

    sign_in()
    expect(page.locator("#page-title")).to_have_text("Học liệu đã duyệt")
    page.click("#nav a[href='#/tests']")
    expect(page.locator("#page-title")).to_have_text("Kiểm tra kiến thức")
    context.clear_cookies()  # the session ends while the learner is on this page
    # The next request (the bell here, or a background refresh that may come first) meets the ended session.
    try:
        page.click("#bell", no_wait_after=True, timeout=3000)
    except Exception:
        pass  # a background request already sent the learner to sign in
    expect(page.locator("#login-form")).to_be_visible()
    sign_in()
    expect(page.locator("#page-title")).to_have_text("Kiểm tra kiến thức")
    assert page.url.endswith("/app#/tests")
    context.close()


def test_a_fragment_that_is_not_an_app_page_is_ignored_after_signing_in(server, browser, signed_in_state):
    context = browser.new_context(locale="vi-VN")
    page = Watched(context.new_page(), server).open("/login#//evil.example/x")
    page.fill("#login-email", EMAIL)
    page.fill("#login-password", PASSWORD)
    page.click("#login-form button[type=submit]")
    expect(page.locator("#view")).to_be_visible()
    expect(page.locator("#page-title")).to_have_text("Bảng điều khiển")
    assert page.url.endswith("/app")
    context.close()


# --- Every main page ---

@pytest.mark.parametrize("path", PAGES)
def test_each_main_page_opens_without_errors_on_desktop(app, path):
    page = app.open(f"/app#{path}")
    wait_ready(page)
    assert page.locator("#view .error-view").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    assert app.errors == []


@pytest.mark.parametrize("path", PAGES)
def test_each_main_page_fits_a_phone_screen(server, browser, signed_in_state, path):
    context = browser.new_context(storage_state=signed_in_state, viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
    watched = Watched(context.new_page(), server)
    page = watched.open(f"/app#{path}")
    wait_ready(page)
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    assert watched.errors == []
    context.close()


# --- Controls in the shell ---

def test_the_theme_button_cycles_light_dark_system(app):
    page = app.open("/app")
    wait_ready(page)
    seen = []
    for _ in range(3):
        page.click("[data-theme-cycle]")
        seen.append(page.get_attribute("[data-theme-cycle]", "data-current"))
    assert sorted(seen) == ["dark", "light", "system"]


def test_the_bell_opens_its_list_and_escape_closes_it(app):
    page = app.open("/app")
    wait_ready(page)
    page.click("#bell")
    assert page.is_visible("#bell-panel") and page.get_attribute("#bell", "aria-expanded") == "true"
    assert page.locator("#bell-panel .bell-empty, #bell-panel .bell-item").count() >= 1
    page.keyboard.press("Escape")
    assert page.is_hidden("#bell-panel")


def test_the_assistant_opens_with_its_suggestions_and_closes(app):
    page = app.open("/app")
    wait_ready(page)
    page.click("#assistant-fab")
    page.wait_for_selector("#assistant-panel:not([hidden]) .chat-welcome")
    assert page.locator("#assistant-panel .chat-chip").count() >= 1
    page.click('#assistant-panel [data-assistant="close"]')
    assert page.is_hidden("#assistant-panel")


def test_the_assistant_welcome_shows_the_animated_robot(app):
    # 5.41: the robot scene replaces the still picture; the face in the header blinks like the "Trợ lý" button.
    page = app.open("/app")
    wait_ready(page)
    page.click("#assistant-fab")
    stage = page.locator("#assistant-panel .chat-stage")
    expect(stage).to_be_visible()
    expect(stage.locator(".as-bot-head img")).to_have_count(2)
    expect(stage.locator("svg.as-bot-body")).to_have_count(1)
    expect(page.locator("#assistant-panel .chat-welcome-art")).to_have_count(0)
    expect(page.locator("#assistant-panel .assistant-title .fab-blink-closed")).to_have_count(1)
    # The robot body's gradients use the panel's own prefix, so they never clash with the dashboard robot's ids.
    expect(page.locator("#as-shell")).to_have_count(1)
    expect(page.locator("#hb-shell")).to_have_count(1)
    assert app.errors == []


def test_the_phone_menu_opens_the_sidebar(server, browser, signed_in_state):
    context = browser.new_context(storage_state=signed_in_state, viewport={"width": 375, "height": 812})
    page = Watched(context.new_page(), server).open("/app")
    wait_ready(page)
    page.click("#menu-btn")
    assert page.get_attribute("#menu-btn", "aria-expanded") == "true"
    page.click("#nav a[href='#/profile']")
    expect(page.locator("#page-title")).to_have_text("Hồ sơ")
    context.close()


def test_the_reminder_filters_switch_without_reloading(app):
    page = app.open("/app#/plan/da/progress")
    wait_ready(page)
    # A learner who has not finished the process sees the call to start it instead.
    if page.locator(".rm-tab").count() == 0:
        assert page.locator("#view .empty").count() == 1
        return
    page.click(".rm-tab[data-kind='MINI_TEST']")
    assert page.get_attribute(".rm-tab[data-kind='MINI_TEST']", "aria-selected") == "true"


# --- Shared components (5.57) ---

def test_moving_to_another_page_puts_focus_on_the_content(app):
    page = app.open("/app")
    wait_ready(page)
    page.click("#nav a[href='#/tests']")
    expect(page.locator("#page-title")).to_have_text("Kiểm tra kiến thức")
    expect(page.locator("#view")).to_be_focused()
    assert app.errors == []


def test_an_empty_list_shows_its_icon_and_a_failed_page_offers_a_retry(app):
    page = app.open("/app#/tests")
    wait_ready(page)
    # A new learner has no attempts yet.
    expect(page.locator("#view .empty .empty-icon")).to_have_count(1)
    page.goto(app.base + "/app#/tests/report/khong-co-bai-nay")
    error = page.locator("#view .error-view")
    expect(error).to_have_attribute("role", "alert")
    expect(error.locator("[data-act='reload']")).to_be_visible()
    # Only the refused lookup itself may be reported.
    assert [item for item in app.errors if "404" not in item] == []


def test_a_dialog_keeps_focus_inside_and_returns_it_to_the_button_that_opened_it(app):
    page = app.open("/app#/profile")
    wait_ready(page)
    page.click("#pf-tab-data")
    opener = page.locator("[data-act='erase']")
    opener.click()
    dialog = page.locator("#modal-root .modal")
    expect(dialog).to_have_attribute("aria-modal", "true")
    expect(dialog).to_have_attribute("aria-labelledby", re.compile(r".+"))
    for _ in range(5):  # Tab only ever reaches the dialog's own buttons
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.closest('#modal-root') !== null")
    page.click("#modal-root [data-dialog='no']")  # "Hủy": nothing is deleted
    expect(dialog).to_have_count(0)
    expect(opener).to_be_focused()
    assert app.errors == []


def test_a_toast_has_a_close_button(app):
    page = app.open("/app#/profile")
    wait_ready(page)
    page.click("form[data-form='account'] button[type=submit]")
    toast_box = page.locator("#toasts .toast").first
    expect(toast_box.locator(".toast-icon")).to_have_count(1)
    toast_box.locator(".toast-close").click()
    expect(page.locator("#toasts .toast")).to_have_count(0)
    assert app.errors == []


def test_starting_the_process_opens_its_first_step(app):
    """Runs last: it starts a Career Adapt process for the test account (in the temporary database)."""
    page = app.open("/app#/process")
    wait_ready(page)
    assert page.locator("#view button.career").count() >= 1
    # Nothing is chosen at first; choosing Data Analyst shows the button that enters the process.
    page.click("#view button.career[data-code='DATA_ANALYST']")
    expect(page.locator("#view button.career[data-code='DATA_ANALYST']")).to_have_attribute("aria-pressed", "true")
    page.click("#view [data-act='enter']")
    expect(page).to_have_url(re.compile(r"#/flow"))  # a hash change, so no page load to wait for
    wait_ready(page)
    expect(page.locator("#view")).not_to_be_empty()
    assert app.errors == []


# --- Admin page (5.40) ---

ADMIN_SECTIONS = {"reviews": "Bài cần duyệt", "contributions": "Câu hỏi đóng góp", "contributors": "Người đóng góp", "jds": "Thư viện JD",
                  "resources": "Học liệu", "tasks": "Đề bài", "activities": "Học phần", "skills": "Kỹ năng", "analytics": "Câu hỏi & hiệu chỉnh",
                  "knowledge": "Kho kiến thức AI", "salary": "Lương tham khảo"}


@pytest.fixture(scope="module")
def admin_state(server, browser, tmp_path_factory):
    """An administrator created in the test server's own accounts database, then signed in through the real form."""
    folder = SERVER_DIRS["folder"]
    env = {key: value for key, value in os.environ.items() if not key.startswith("CAREERADAPT_")}
    env.update({"CAREERADAPT_DB": str(folder / "careeradapt.sqlite3"), "CAREERADAPT_ACCOUNTS_DB": str(folder / "accounts.sqlite3"), "PYTHONIOENCODING": "utf-8"})
    script = f"from backend.accounts import create_account; create_account({ADMIN_EMAIL!r}, {ADMIN_NAME!r}, {ADMIN_PASSWORD!r}, role='admin')"
    subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env, check=True, capture_output=True)
    context = browser.new_context(locale="vi-VN")
    page = context.new_page()
    page.goto(server + "/login")
    page.fill("#login-email", ADMIN_EMAIL)
    page.fill("#login-password", ADMIN_PASSWORD)
    page.click("#login-form button[type=submit]")
    page.wait_for_url("**/app**")
    state = tmp_path_factory.mktemp("ui-admin") / "state.json"
    context.storage_state(path=str(state))
    context.close()
    return str(state)


@pytest.fixture
def admin(server, browser, admin_state):
    context = browser.new_context(storage_state=admin_state, locale="vi-VN", viewport={"width": 1440, "height": 900})
    watched = Watched(context.new_page(), server)
    yield watched
    context.close()


def test_every_admin_section_opens_with_its_header_and_no_error(admin):
    page = admin.open("/app#/admin")
    expect(page.locator(".adm-nav-item")).to_have_count(len(ADMIN_SECTIONS))
    expect(page.locator(".rm-kpi")).to_have_count(4)
    for section, label in ADMIN_SECTIONS.items():
        page.click(f'.adm-nav-item[data-tab="{section}"]')
        expect(page.locator(".adm-pane-head h2")).to_have_text(label)
        expect(page.locator("#admin-pane .adm-skeleton")).to_have_count(0)
        expect(page.locator(f'.adm-nav-item[data-tab="{section}"]')).to_have_attribute("aria-selected", "true")
        assert page.url.endswith(f"#/admin/{section}")
    assert admin.errors == []


def test_a_section_link_opens_that_section(admin):
    page = admin.open("/app#/admin/knowledge")
    expect(page.locator(".adm-pane-head h2")).to_have_text("Kho kiến thức AI")
    expect(page.locator('.adm-nav-item[data-tab="knowledge"]')).to_have_attribute("aria-selected", "true")
    # Searching narrows the list; a query that matches nothing shows the empty note.
    page.fill("[data-adm-search]", "zzz-khong-co-tai-lieu-nay")
    expect(page.locator("[data-adm-empty]")).to_be_visible()
    assert admin.errors == []


def test_the_optional_skill_with_weight_zero_can_be_saved(admin):
    page = admin.open("/app#/admin/skills")
    page.click('[data-act="skill-edit"][data-id="STATISTICS"]')
    expect(page.locator('form[data-form="skill"] input[name="weight"]')).to_have_value("0")
    page.click('form[data-form="skill"] button[type="submit"]')
    expect(page.locator(".toast").filter(has_text="Đã lưu kỹ năng.")).to_have_count(1)
    expect(page.locator('form[data-form="skill"]')).to_have_count(0)
    assert admin.errors == []


def test_arrow_keys_move_between_the_admin_sections(admin):
    # 5.57: every tab list answers the arrow keys, Home and End, not only the one on Hồ sơ.
    page = admin.open("/app#/admin/reviews")
    expect(page.locator(".adm-pane-head h2")).to_have_text("Bài cần duyệt")
    page.focus('.adm-nav-item[data-tab="reviews"]')
    page.keyboard.press("ArrowDown")
    expect(page.locator('.adm-nav-item[data-tab="contributions"]')).to_have_attribute("aria-selected", "true")
    expect(page.locator(".adm-pane-head h2")).to_have_text("Câu hỏi đóng góp")
    page.keyboard.press("End")
    last = page.locator(".adm-nav-item").last
    expect(last).to_have_attribute("aria-selected", "true")
    expect(last).to_be_focused()
    assert admin.errors == []


def test_the_calibration_form_offers_every_skill(admin):
    page = admin.open("/app#/admin/analytics")
    expect(page.locator('form[data-form="calibration"] select[name="skill_code"] option[value="STATISTICS"]')).to_have_count(1)


def test_the_admin_sections_fit_one_row_on_a_phone(server, browser, admin_state):
    context = browser.new_context(storage_state=admin_state, locale="vi-VN", viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    watched = Watched(context.new_page(), server)
    page = watched.open("/app#/admin")
    nav = page.locator(".adm-nav")
    expect(nav).to_be_visible()
    assert nav.bounding_box()["height"] < 80
    page.click('.adm-nav-item[data-tab="resources"]')
    expect(page.locator(".adm-pane-head h2")).to_have_text("Học liệu")
    assert watched.errors == []
    context.close()



# --- Robot expressions (5.43) ---

def test_the_sign_in_robot_changes_its_expression_with_what_happens(server, browser, signed_in_state):
    context = browser.new_context(locale="vi-VN")
    watched = Watched(context.new_page(), server)
    page = watched.open("/login")
    face = page.locator(".login-bot-face")
    expect(face).to_have_attribute("data-expr", "happy")
    expect(face.locator("svg.xbot-face")).to_have_count(1)
    page.click("#login-password")
    expect(face).to_have_attribute("data-expr", "shy")
    page.fill("#login-email", EMAIL)
    page.fill("#login-password", "Sai-Mat-Khau#1")
    page.click("#login-form button[type=submit]")
    page.wait_for_selector("#login-message:not([hidden])")
    expect(face).to_have_attribute("data-expr", "worried")
    # Only the refused sign-in itself may be reported; no script or policy error.
    assert [error for error in watched.errors if "401" not in error] == []
    context.close()
