"""Audit 2026-11-04: malformed input must be rejected (422/404), never crash (500),
and one learner must never reach another learner's attempts, JDs, reminders or checks."""
import pytest

from backend.store import store
from v4_helpers import STUDENT, STUDENT_2, STUDENT_ID, client

T = "/api/v1/tests"
JD_TEXT = """Data Analyst Intern
Yêu cầu: thành thạo SQL để truy vấn dữ liệu, làm sạch dữ liệu, trực quan hóa bằng biểu đồ, Python pandas cơ bản, viết báo cáo rõ ràng."""


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    yield


def start_attempt(headers=STUDENT, blueprint="SKILL_CHECK_SQL"):
    response = client.post(f"{T}/attempts", json={"blueprint_id": blueprint}, headers=headers)
    assert response.status_code in (200, 201), response.text
    return response.json()


def items_of(attempt):
    return {item["type"]: item for item in attempt["items"]}


def any_blueprint_with(kind):
    for blueprint in client.get(f"{T}/blueprints", headers=STUDENT).json()["blueprints"]:
        attempt = start_attempt(blueprint=blueprint["blueprint_id"])
        found = next((item for item in attempt["items"] if item["type"] == kind), None)
        if found:
            return attempt, found
    pytest.skip(f"no blueprint has a {kind} item")


@pytest.mark.parametrize("kind, value", [
    ("single", ["a"]), ("single", {"x": 1}), ("single", 5),
    ("multiple", {"x": 1}), ("multiple", [["a"]]), ("multiple", "a"),
    ("ordering", {"x": 1}), ("ordering", [1, 2]),
    ("numeric", {"x": 1}), ("numeric", ["1"]), ("numeric", True),
])
def test_malformed_test_center_answers_are_rejected(kind, value):
    attempt, item = any_blueprint_with(kind)
    response = client.put(f"{T}/attempts/{attempt['attempt_id']}/responses/{item['item_id']}", json={"value": value}, headers=STUDENT)
    assert response.status_code == 422, (kind, value, response.status_code, response.text)


def test_another_learner_cannot_touch_a_test_attempt():
    attempt = start_attempt()
    item = attempt["items"][0]
    base = f"{T}/attempts/{attempt['attempt_id']}"
    assert client.get(base, headers=STUDENT_2).status_code == 404
    assert client.put(f"{base}/responses/{item['item_id']}", json={"value": None}, headers=STUDENT_2).status_code == 404
    assert client.post(f"{base}/events", json={"type": "paste"}, headers=STUDENT_2).status_code == 404
    assert client.post(f"{base}/submit", headers=STUDENT_2).status_code == 404
    assert client.get(f"{base}/report", headers=STUDENT_2).status_code == 404
    assert client.get(f"{T}/attempts", headers=STUDENT_2).json()["attempts"] == []
    # The owner's attempt is still open and unchanged.
    assert client.get(base, headers=STUDENT).json()["status"] == "IN_PROGRESS"


def test_another_learner_cannot_read_or_delete_an_imported_jd():
    imported = client.post("/jds/import", data={"text": JD_TEXT, "title": "JD riêng"}, headers=STUDENT)
    assert imported.status_code in (200, 201), imported.text
    jd = imported.json()
    assert client.get(f"/jds/{jd['jd_id']}/versions", headers=STUDENT_2).status_code == 404
    assert client.get(f"/jds/{jd['jd_id']}/versions/{jd['jd_version']}", headers=STUDENT_2).status_code == 404
    assert client.delete(f"/jds/{jd['jd_id']}", headers=STUDENT_2).status_code == 404
    assert client.get(f"/jds/{jd['jd_id']}/versions", headers=STUDENT).status_code == 200


def test_unknown_ids_give_404_not_500():
    for path in ("/activities/NOPE/detail", "/micro-tests/NOPE", "/api/v1/tests/attempts/NOPE", "/jds/NOPE/versions"):
        assert client.get(path, headers=STUDENT).status_code == 404, path
    assert client.post("/activities/NOPE/knowledge-check", json={"confirm": True}, headers=STUDENT).status_code == 404
    assert client.post("/me/reminders/NOPE/dismiss", headers=STUDENT).status_code == 404
    assert client.post("/me/reminders/NOPE/snooze", json={"days": 1}, headers=STUDENT).status_code == 404
    assert client.post("/micro-tests/NOPE/ai-feedback", headers=STUDENT).status_code == 404


@pytest.mark.parametrize("body", [
    {"status": "IN_PROGRESS", "progress_percent": 150}, {"status": "IN_PROGRESS", "progress_percent": -5},
    {"status": "DONE", "progress_percent": 10}, {"status": "IN_PROGRESS", "progress_percent": 10, "actual_hours": -1},
    {"status": "IN_PROGRESS", "progress_percent": 10, "notes": "x" * 5000},
])
def test_invalid_progress_updates_are_rejected(body):
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {"SQL": {"level": 1}}
    assert client.post("/roadmaps", headers=STUDENT).status_code in (200, 201)
    assert client.patch("/activities/ACT_SQL_01/progress", json=body, headers=STUDENT).status_code == 422


def test_progress_cannot_be_marked_completed_without_the_knowledge_check():
    """Completing a lesson goes through the knowledge check, which is what may change mastery."""
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {"SQL": {"level": 1}}
    assert client.post("/roadmaps", headers=STUDENT).status_code in (200, 201)
    client.patch("/activities/ACT_SQL_01/progress", json={"status": "COMPLETED", "progress_percent": 100}, headers=STUDENT)
    assert store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] == 1


def roadmap_for_sql():
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {"SQL": {"level": 1}}
    assert client.post("/roadmaps", headers=STUDENT).status_code in (200, 201)


@pytest.mark.parametrize("body", [{}, {"x": None}, {"progress_percent": 100}])
def test_a_progress_update_without_a_status_is_refused(body):
    """Before the audit an empty body defaulted to COMPLETED 100% and scheduled a re-check."""
    roadmap_for_sql()
    assert client.patch("/activities/ACT_SQL_01/progress", json=body, headers=STUDENT).status_code == 422
    assert client.get("/me/roadmap", headers=STUDENT).json()["activity_progress"].get("ACT_SQL_01") is None


def test_in_progress_without_a_percent_keeps_the_saved_percent():
    roadmap_for_sql()
    client.patch("/activities/ACT_SQL_01/progress", json={"status": "IN_PROGRESS", "progress_percent": 40}, headers=STUDENT)
    response = client.patch("/activities/ACT_SQL_01/progress", json={"status": "IN_PROGRESS"}, headers=STUDENT).json()
    assert (response["status"], response["progress_percent"]) == ("IN_PROGRESS", 40)
    assert response["checkin"] is None
    assert client.patch("/activities/ACT_SQL_01/progress", json={"status": "COMPLETED"}, headers=STUDENT).json()["progress_percent"] == 100


ACTIVITY = {"activity_id": "ACT_AUDIT_01", "title": "Học phần kiểm toán", "target_skill": "SQL", "target_level": 2, "estimated_hours": 2.0}


@pytest.mark.parametrize("change", [
    {"target_level": 9}, {"target_level": 0}, {"estimated_hours": 0}, {"estimated_hours": -3},
    {"target_skill": "UNKNOWN_SKILL"}, {"activity_id": "bad id with spaces"}, {"title": ""},
])
def test_admin_cannot_save_an_activity_outside_the_model(change):
    from v4_helpers import ADMIN
    response = client.post("/admin/activities", json={**ACTIVITY, **change}, headers=ADMIN)
    assert response.status_code == 422, (change, response.status_code, response.text)


def test_admin_can_still_save_a_valid_activity():
    from v4_helpers import ADMIN
    response = client.post("/admin/activities", json=ACTIVITY, headers=ADMIN)
    assert response.status_code == 201, response.text
    assert client.delete("/admin/activities/ACT_AUDIT_01", headers=ADMIN).status_code == 200


def test_repeated_wrong_passwords_lock_the_email_for_a_while():
    """Misuse case "Dò mật khẩu": the throttle in accounts.begin_login_attempt had no test of its own."""
    from contextlib import closing
    from fastapi.testclient import TestClient
    from backend.accounts import MAX_LOGIN_FAILURES, _connect
    from backend.main import app
    from test_auth_sessions import _email, _login, _register

    def clear():
        with closing(_connect()) as conn:
            conn.execute("DELETE FROM registration_attempts")
            conn.execute("DELETE FROM login_attempts")

    clear()
    try:
        browser = TestClient(app)
        target, other = _email("guess"), _email("other")
        assert _register(browser, target).status_code == 201
        assert _register(browser, other).status_code == 201
        for _ in range(MAX_LOGIN_FAILURES):
            assert _login(browser, target, "Wrong-Pass-999").status_code == 401
        # Even the right password is refused until the window passes; the message does not say whether it was right.
        locked = _login(browser, target)
        assert locked.status_code == 429
        assert locked.json()["error"]["code"] == "LOGIN_RATE_LIMITED"
        assert _login(TestClient(app), other).status_code == 200
    finally:
        clear()


def test_html_in_a_jd_title_is_stored_as_text():
    title = '<img src=x onerror=alert(1)>'
    jd = client.post("/jds/import", data={"text": JD_TEXT, "title": title}, headers=STUDENT).json()
    view = client.get(f"/jds/{jd['jd_id']}/versions/{jd['jd_version']}", headers=STUDENT).json()
    # The API returns data; escaping is the page's job (core.esc). The value must not be altered or executed server-side.
    assert title in str(view)


def test_a_long_ai_jd_summary_is_cut_on_a_whole_line(monkeypatch):
    """The JD summary is shown as a lead line plus bullets, so the 900-character cap must not cut a bullet in half."""
    from backend.ai_service import assessment_provider
    lines = ["Chuyên viên phân tích dữ liệu"] + [f"- Yêu cầu số {index}: " + "x" * 60 for index in range(20)]
    monkeypatch.setattr(assessment_provider, "is_enabled", lambda: True)
    monkeypatch.setattr(assessment_provider.config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(assessment_provider, "_call_openai", lambda *args: {"summary": "\n".join(lines)})
    text = assessment_provider.summarize_jd({"name": "X"}, "Nội dung JD")["text"]
    assert len(text) <= 900
    assert all(line in lines for line in text.split("\n"))


def test_a_locked_assistant_says_why_and_links_to_the_open_check():
    """The sidebar used to just vanish; the status now carries the reason and where to go back to."""
    roadmap_for_sql()
    check = client.post("/activities/ACT_SQL_01/knowledge-check", json={"confirm": True}, headers=STUDENT).json()["lesson_check"]
    client.get(f"/micro-tests/{check['micro_id']}", headers=STUDENT)
    status = client.get("/api/v1/assistant/status", headers=STUDENT).json()
    assert status["blocked"] is True
    assert "mini-test" in status["block_reason"]
    assert status["block_link"] == f"#/mini/{check['micro_id']}"
    assert client.get("/api/v1/assistant/status", headers=STUDENT_2).json()["blocked"] is False
