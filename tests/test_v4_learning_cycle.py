"""V4.0 acceptance: review cycles, reminders, mini-tests (RM-01..RM-04, F10, F20, F21)."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.clock import set_clock
from backend.learning_cycle_service import compute_due_at, run_scan, select_micro_items
from backend.store import store
from v4_helpers import ADMIN, STUDENT, STUDENT_2, STUDENT_ID, client

START = datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc)  # 10:00 in Asia/Ho_Chi_Minh


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    fake = Clock()
    set_clock(fake)
    yield fake
    set_clock(None)


@pytest.fixture(autouse=True)
def fresh():
    store.reset()
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {code: {"level": level} for code, level in {"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2}.items()}
    client.post("/roadmaps", headers=STUDENT)
    yield
    set_clock(None)


def set_cycle(days=7, activity="ACT_SQL_01"):
    resp = client.patch(f"/activities/{activity}/schedule", json={"action": "SET_CYCLE", "cycle_days": days}, headers=STUDENT)
    assert resp.status_code == 200, resp.text
    return resp.json()


def reminders():
    return client.get("/me/reminders", headers=STUDENT).json()


def correct_response(item):
    return item["answer"]


def answer_key(micro_id):
    row = store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (micro_id,))
    return {item["item_id"]: item["answer"] for item in json.loads(row["payload"])["items"]}


def wrong_answers(micro_id):
    row = store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (micro_id,))
    responses = {}
    for item in json.loads(row["payload"])["items"]:
        if item["type"] == "single":
            responses[item["item_id"]] = next(option["id"] for option in item["options"] if option["id"] != item["answer"])
        elif item["type"] == "numeric":
            responses[item["item_id"]] = float(item["answer"]) + 12345
        else:
            responses[item["item_id"]] = [option["id"] for option in item["options"] if option["id"] not in item["answer"]][:1] or list(reversed(item["answer"]))
    return responses


# RM-01
def test_rm01_seven_day_cycle_uses_the_timezone_and_gives_one_reminder_one_test(clock):
    checkin = set_cycle(7)
    # 2 Nov + 7 days at 08:00 in Ho Chi Minh is 01:00 UTC on 9 Nov.
    assert checkin["due_at"].startswith("2026-11-09T01:00:00")
    assert reminders()["unread_count"] == 0 or all(item["kind"] != "MINI_TEST" for item in reminders()["active"])
    clock.now = datetime(2026, 11, 9, 0, 59, tzinfo=timezone.utc)
    assert not [item for item in reminders()["active"] if item["kind"] == "MINI_TEST"]
    clock.advance(minutes=2)
    for _ in range(5):
        run_scan()
        run_scan(STUDENT_ID)
    data = reminders()
    assert len([item for item in data["active"] if item["kind"] == "MINI_TEST"]) == 1
    assert len(data["pending_mini_tests"]) == 1
    assert store.db.one("SELECT COUNT(*) AS n FROM micro_assessments")["n"] == 1


def test_due_date_changes_with_timezone():
    new_york = compute_due_at(date(2026, 11, 2), 7, "America/New_York")
    assert new_york == datetime(2026, 11, 9, 13, 0, tzinfo=timezone.utc)
    assert compute_due_at(date(2026, 11, 2), 7, "Asia/Ho_Chi_Minh") == datetime(2026, 11, 9, 1, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("days", [3, 7, 14, 30, 45])
def test_preset_and_custom_cycles(clock, days):
    assert set_cycle(days)["cycle_days"] == days


@pytest.mark.parametrize("days", [0, -1, 91])
def test_cycle_outside_the_limits_is_refused(days):
    assert client.patch("/activities/ACT_SQL_01/schedule", json={"cycle_days": days}, headers=STUDENT).status_code == 422


# RM-02
def test_rm02_changing_the_cycle_replaces_the_old_schedule(clock):
    first = set_cycle(7)
    second = set_cycle(14)
    assert second["due_at"] > first["due_at"]
    clock.advance(days=8)
    assert not [item for item in reminders()["active"] if item["kind"] == "MINI_TEST"]  # nothing from the old date
    old = store.db.one("SELECT status, superseded_by FROM learning_checkins WHERE checkin_id = ?", (first["checkin_id"],))
    assert old["status"] == "SUPERSEDED" and old["superseded_by"] == second["checkin_id"]  # history kept
    clock.advance(days=7)
    assert len([item for item in reminders()["active"] if item["kind"] == "MINI_TEST"]) == 1


def test_changing_the_cycle_after_it_came_due_retires_the_old_reminder(clock):
    set_cycle(3)
    clock.advance(days=4)
    assert reminders()["pending_mini_tests"]
    set_cycle(7)
    data = reminders()
    assert not data["pending_mini_tests"] and not [item for item in data["active"] if item["kind"] == "MINI_TEST"]


def test_rm02_postponing_moves_the_date_without_a_duplicate(clock):
    checkin = set_cycle(3)
    clock.advance(days=4)
    assert len(reminders()["pending_mini_tests"]) == 1
    postponed = client.patch("/activities/ACT_SQL_01/schedule", json={"action": "SNOOZE", "snooze_days": 2}, headers=STUDENT).json()
    assert postponed["due_at"] > checkin["due_at"]
    assert not reminders()["pending_mini_tests"]
    clock.advance(days=2, minutes=1)
    assert len([item for item in reminders()["active"] if item["kind"] == "MINI_TEST"]) == 1


def test_snoozing_a_reminder_brings_back_the_same_row(clock):
    set_cycle(3)
    clock.advance(days=4)
    reminder = next(item for item in reminders()["active"] if item["kind"] == "MINI_TEST")
    resp = client.post(f"/me/reminders/{reminder['reminder_id']}/snooze", json={"days": 1}, headers=STUDENT)
    assert resp.status_code == 200
    data = reminders()
    assert not [item for item in data["active"] if item["kind"] == "MINI_TEST"] and len(data["snoozed"]) == 1
    clock.advance(days=1, minutes=1)
    again = [item for item in reminders()["active"] if item["kind"] == "MINI_TEST"]
    assert [item["reminder_id"] for item in again] == [reminder["reminder_id"]]
    assert store.db.one("SELECT COUNT(*) AS n FROM reminder_jobs WHERE kind = 'MINI_TEST'")["n"] == 1


def test_database_refuses_a_second_reminder_for_the_same_due_date(clock):
    set_cycle(3)
    clock.advance(days=4)
    run_scan()
    row = store.db.one("SELECT * FROM reminder_jobs WHERE kind = 'MINI_TEST'")
    inserted = store.db.execute(
        "INSERT OR IGNORE INTO reminder_jobs(reminder_id, user_id, kind, dedupe_key, scheduled_at, status, title, updated_at) VALUES ('x', ?, 'MINI_TEST', ?, 't', 'ACTIVE', 't', 't')",
        (row["user_id"], row["dedupe_key"]),
    ).rowcount
    assert inserted == 0


def test_finished_or_cancelled_cycles_send_nothing(clock):
    set_cycle(3)
    client.patch("/activities/ACT_SQL_01/schedule", json={"action": "CANCEL"}, headers=STUDENT)
    clock.advance(days=4)
    assert not [item for item in reminders()["active"] if item["kind"] == "MINI_TEST"]


def test_marking_an_activity_studied_does_not_start_the_review_clock(clock):
    """Roadmap 2.0: the review is counted from the passed completion check, not from "studied"
    (tests/test_learning_roadmap_2.py covers the scheduling after a pass)."""
    response = client.patch("/activities/ACT_SQL_01/progress", json={"status": "COMPLETED"}, headers=STUDENT).json()
    assert response["checkin"] is None
    assert client.get("/me/checkins", headers=STUDENT).json() == []


def test_mini_test_questions_match_the_skill_and_avoid_recent_items():
    items = select_micro_items("SQL", 2, set(), seed=1)
    assert 3 <= len(items) <= 5
    assert all(item["skill_code"] == "SQL" and item["level"] <= 2 for item in items)
    used = {item["item_id"] for item in items}
    assert not used & {item["item_id"] for item in select_micro_items("SQL", 2, used, seed=2)}


def test_mini_test_form_hides_the_answers(clock):
    set_cycle(3)
    clock.advance(days=4)
    micro_id = reminders()["pending_mini_tests"][0]["micro_id"]
    data = client.get(f"/micro-tests/{micro_id}", headers=STUDENT).json()
    assert data["items"] and 5 <= data["time_limit_minutes"] <= 10
    text = json.dumps(data, ensure_ascii=False)
    assert '"answer"' not in text and "explanation" not in text


def due_micro(clock):
    set_cycle(3)
    clock.advance(days=4)
    return reminders()["pending_mini_tests"][0]["micro_id"]


def level():
    return store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"]


def test_passing_records_evidence_and_can_raise_one_level(clock):
    micro_id = due_micro(clock)
    result = client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": answer_key(micro_id), "idempotency_key": "k1"}, headers=STUDENT).json()
    assert result["status"] == "PASSED" and result["score"] == 100
    assert result["previous_level"] == 1 and result["current_level"] == level() == 2
    assert store.skill_evidence(STUDENT_ID, "SQL")[-1]["source_type"] == "MINI_TEST"
    data = reminders()
    assert not data["pending_mini_tests"] and not [item for item in data["active"] if item["kind"] == "MINI_TEST"]
    assert "không phải chứng chỉ" in result["scope_note"]


def test_rm03_failing_shows_weak_parts_and_resources_without_mastery(clock):
    micro_id = due_micro(clock)
    result = client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": wrong_answers(micro_id)}, headers=STUDENT).json()
    assert result["status"] == "FAILED" and result["passed"] is False
    assert result["weak_topics"] and result["review_resources"] and result["suggested_cycle_days"] in (3, 7)
    assert all(resource["url"] for resource in result["review_resources"])
    assert level() == 1  # never lowers or raises on a fail
    assert store.skill_evidence(STUDENT_ID) == []


def test_empty_mini_test_is_incomplete_and_can_be_retaken(clock):
    micro_id = due_micro(clock)
    result = client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": {}}, headers=STUDENT).json()
    assert result["status"] == "INCOMPLETE" and result["score"] is None
    assert level() == 1
    assert client.get(f"/micro-tests/{micro_id}", headers=STUDENT).json()["status"] == "PENDING"
    assert client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": answer_key(micro_id)}, headers=STUDENT).json()["status"] == "PASSED"


def test_one_blank_item_scores_zero_not_correct(clock):
    micro_id = due_micro(clock)
    responses = answer_key(micro_id)
    responses.pop(next(iter(responses)))
    result = client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": responses}, headers=STUDENT).json()
    assert result["answered"] == result["total"] - 1 and result["score"] < 100


def test_double_submit_counts_once(clock):
    micro_id = due_micro(clock)
    body = {"responses": answer_key(micro_id), "idempotency_key": "same"}
    first = client.post(f"/micro-tests/{micro_id}/submissions", json=body, headers=STUDENT).json()
    second = client.post(f"/micro-tests/{micro_id}/submissions", json=body, headers=STUDENT).json()
    assert second["is_duplicate"] is True and second["score"] == first["score"]
    assert len(store.skill_evidence(STUDENT_ID, "SQL")) == 1
    assert client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": {}}, headers=STUDENT).status_code == 409


def test_a_mini_test_cannot_jump_two_levels(clock):
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] = 0
    micro_id = due_micro(clock)
    result = client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": answer_key(micro_id)}, headers=STUDENT).json()
    assert result["current_level"] == 1


def sql_items(*levels):
    return [item for item in store.question_items if item["skill_code"] == "SQL" and item["level"] in levels]


@pytest.mark.parametrize("skill_code", ["SQL", "PYTHON", "DATA_QUALITY", "DATA_VIZ", "WRITTEN_COMM"])
@pytest.mark.parametrize("max_level", [1, 2, 3])
def test_mini_test_form_measures_every_level_up_to_the_target(skill_code, max_level):
    for seed in range(200):
        items = select_micro_items(skill_code, max_level, set(), seed=seed)
        assert len(items) == 4 and len({item["item_id"] for item in items}) == 4
        assert {item["level"] for item in items} == set(range(1, max_level + 1))
        assert sum(item["level"] == max_level for item in items) >= 2  # still shows the outcome studied


def test_mini_test_reuses_a_seen_item_only_when_a_level_has_no_fresh_one():
    level_one = {item["item_id"] for item in sql_items(1)}
    for seed in range(50):
        items = select_micro_items("SQL", 2, level_one, seed=seed)
        assert [item["level"] for item in items].count(1) == 1
        assert {item["level"] for item in items} == {1, 2}


def test_perfect_score_raises_one_level_when_recent_tests_used_every_level_one_item(clock, monkeypatch):
    # Every item of level 1 was seen recently, the form the old selection turned into level 2 only.
    monkeypatch.setattr("backend.learning_cycle_service._recent_items", lambda *_: {item["item_id"] for item in sql_items(1)})
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] = 0
    micro_id = due_micro(clock)
    result = client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": answer_key(micro_id)}, headers=STUDENT).json()
    assert result["score"] == 100 and result["current_level"] == level() == 1


def issued_without_level_one(clock):
    """A form stored before every level was covered: new selection cannot repair it."""
    micro_id = due_micro(clock)
    payload = json.loads(store.db.one("SELECT payload FROM micro_assessments WHERE micro_id = ?", (micro_id,))["payload"])
    payload["items"] = sql_items(2)
    store.db.execute("UPDATE micro_assessments SET payload = ? WHERE micro_id = ?", (json.dumps(payload), micro_id))
    return micro_id


@pytest.mark.parametrize("before", [0, 1, 2])
def test_issued_form_without_level_one_never_lowers_a_level(clock, before):
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"]["level"] = before
    micro_id = issued_without_level_one(clock)
    result = client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": answer_key(micro_id)}, headers=STUDENT).json()
    assert result["status"] == "PASSED" and result["current_level"] == level() == before


def test_issued_form_without_level_one_does_not_certify_an_unassessed_learner(clock):
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"].pop("SQL")
    micro_id = issued_without_level_one(clock)
    result = client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": answer_key(micro_id)}, headers=STUDENT).json()
    assert result["status"] == "PASSED" and result["current_level"] is None
    assert "SQL" not in store.get_or_create_profile(STUDENT_ID)["assessed_skills"]
    assert store.skill_evidence(STUDENT_ID, "SQL") == []


def test_another_learner_cannot_open_or_submit(clock):
    micro_id = due_micro(clock)
    assert client.get(f"/micro-tests/{micro_id}", headers=STUDENT_2).status_code == 404
    assert client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": {}}, headers=STUDENT_2).status_code == 404
    reminder = next(item for item in reminders()["active"] if item["kind"] == "MINI_TEST")
    assert client.post(f"/me/reminders/{reminder['reminder_id']}/snooze", json={"days": 1}, headers=STUDENT_2).status_code == 404


def test_due_mini_test_reminder_cannot_be_dismissed_away(clock):
    due_micro(clock)
    reminder = next(item for item in reminders()["active"] if item["kind"] == "MINI_TEST")
    assert client.post(f"/me/reminders/{reminder['reminder_id']}/dismiss", headers=STUDENT).status_code == 409


def test_overdue_activity_reminds_once_and_clears_on_completion(clock):
    client.post("/roadmaps", headers=STUDENT)
    clock.advance(days=30)
    client.post("/roadmaps", headers=STUDENT)
    plan = store.roadmaps[STUDENT_ID]["activity_plan"]
    assert plan
    # Plans are dated from when they are made, so step past this one.
    clock.advance(days=30)
    for _ in range(3):
        run_scan(STUDENT_ID)
    overdue = [item for item in reminders()["active"] if item["kind"] == "ACTIVITY_DUE" and item["title"].startswith("Quá hạn")]
    assert len(overdue) == 1 and "không phải đánh giá năng lực" in overdue[0]["body"]
    client.patch("/activities/ACT_SQL_01/progress", json={"status": "COMPLETED"}, headers=STUDENT)
    assert not [item for item in reminders()["active"] if item["kind"] == "ACTIVITY_DUE"]


def test_learner_can_turn_a_reminder_kind_off(clock):
    client.put("/me/reminder-preferences", json={"enabled_kinds": {"MINI_TEST": False}}, headers=STUDENT)
    due = due_micro(clock)
    assert due  # the test is still available
    assert not [item for item in reminders()["active"] if item["kind"] == "MINI_TEST"]


def test_invalid_preferences_are_refused():
    assert client.put("/me/reminder-preferences", json={"timezone": "Mars/Base"}, headers=STUDENT).status_code == 422
    assert client.put("/me/reminder-preferences", json={"default_cycle_days": 400}, headers=STUDENT).status_code == 422
    assert client.put("/me/reminder-preferences", json={"default_cycle_days": 14}, headers=STUDENT).json()["default_cycle_days"] == 14


def test_simulation_is_off_unless_demo_tools_are_enabled(clock, monkeypatch):
    set_cycle(7)
    assert client.patch("/activities/ACT_SQL_01/schedule", json={"action": "SIMULATE_DUE"}, headers=STUDENT).status_code == 403
    monkeypatch.setenv("CAREERADAPT_ENABLE_DEMO_TOOLS", "true")
    assert client.patch("/activities/ACT_SQL_01/schedule", json={"action": "SIMULATE_DUE"}, headers=STUDENT).status_code == 200
    assert reminders()["pending_mini_tests"]
    monkeypatch.setenv("CAREERADAPT_ENV", "production")
    assert client.get("/system/capabilities", headers=STUDENT).json()["demo_tools_enabled"] is False


def test_history_shows_levels_tests_roadmap_and_progress(clock):
    micro_id = due_micro(clock)
    client.post(f"/micro-tests/{micro_id}/submissions", json={"responses": answer_key(micro_id)}, headers=STUDENT)
    events = {item["event"] for item in client.get("/me/history", headers=STUDENT).json()}
    assert {"GENERATE_ROADMAP", "CYCLE_SET", "MINI_TEST_SUBMITTED"} <= events
    assert client.get("/me/skill-history", headers=STUDENT).json()[0]["source_type"] == "MINI_TEST"
    assert client.get("/me/checkins", headers=STUDENT).json()[0]["micro_status"] == "PASSED"


def test_mini_test_is_unavailable_rather_than_empty_when_the_bank_is_short(clock):
    for item in store.question_items:
        if item["skill_code"] == "SQL":
            item["status"] = "RETIRED"
    set_cycle(3)
    clock.advance(days=4)
    run_scan(STUDENT_ID)
    assert store.db.one("SELECT status FROM micro_assessments")["status"] == "UNAVAILABLE"
    assert client.get("/admin/reviews", headers=ADMIN).status_code == 200
