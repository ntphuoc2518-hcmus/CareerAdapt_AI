"""Reminders (5.29): faults found by testing the old page, and the new actions behind the redesigned one."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.clock import set_clock
from backend.store import store
from v4_helpers import STUDENT, STUDENT_2, STUDENT_ID, client

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
    store.reset()
    profile = store.get_or_create_profile(STUDENT_ID)
    profile["assessed_skills"] = {code: {"level": level} for code, level in {"SQL": 1, "DATA_QUALITY": 2, "PYTHON": 1, "DATA_VIZ": 2, "WRITTEN_COMM": 2}.items()}
    client.post("/roadmaps", headers=STUDENT)
    yield fake
    set_clock(None)
    store.reset()


def reminders(headers=STUDENT):
    return client.get("/me/reminders", headers=headers).json()


def first_lesson():
    plan = store.roadmaps[STUDENT_ID]["activity_plan"]
    activity_id, item = min(plan.items(), key=lambda pair: pair[1]["planned_end"])
    return activity_id, datetime.fromisoformat(item["planned_end"] + "T05:00:00+00:00")


def overdue(clock, days=2):
    activity_id, end = first_lesson()
    clock.now = end + timedelta(days=days)
    return next(item for item in reminders()["active"] if item["activity_id"] == activity_id)


def due_review(clock):
    client.patch("/activities/ACT_SQL_01/schedule", json={"action": "SET_CYCLE", "cycle_days": 1}, headers=STUDENT)
    clock.advance(days=2)
    return next(item for item in reminders()["active"] if item["kind"] == "MINI_TEST")


# --- Faults found by testing ---

def test_a_lesson_never_shows_due_soon_and_overdue_together(clock):
    activity_id, end = first_lesson()
    clock.now = end - timedelta(days=1)
    soon = [item for item in reminders()["active"] if item["activity_id"] == activity_id]
    assert [item["state"] for item in soon] == ["DUE_SOON"] and soon[0]["days"] == 1
    clock.now = end + timedelta(days=2)
    late = [item for item in reminders()["active"] if item["activity_id"] == activity_id]
    assert [item["state"] for item in late] == ["OVERDUE"] and late[0]["days"] == -2
    assert store.db.one("SELECT status FROM reminder_jobs WHERE reminder_id = ?", (soon[0]["reminder_id"],))["status"] == "SUPERSEDED"


def test_the_due_date_in_the_text_is_written_day_first(clock):
    activity_id, end = first_lesson()
    clock.now = end - timedelta(days=1)
    item = next(item for item in reminders()["active"] if item["activity_id"] == activity_id)
    assert end.strftime("%d/%m/%Y") in item["body"] and end.strftime("%Y-%m-%d") not in item["body"]


def test_a_new_roadmap_version_retires_the_reminders_of_the_old_plan(clock):
    old = overdue(clock)
    store.get_or_create_profile(STUDENT_ID)["assessed_skills"]["SQL"] = {"level": 0}
    client.post("/roadmaps", headers=STUDENT)
    assert store.roadmaps[STUDENT_ID]["roadmap_version"] > 1
    assert old["reminder_id"] not in {item["reminder_id"] for item in reminders()["active"]}
    assert store.db.one("SELECT status FROM reminder_jobs WHERE reminder_id = ?", (old["reminder_id"],))["status"] == "SUPERSEDED"


def test_turning_a_kind_off_hides_what_is_showing_and_turning_it_on_brings_it_back(clock):
    item = overdue(clock)
    client.put("/me/reminder-preferences", json={"enabled_kinds": {"ACTIVITY_DUE": False}}, headers=STUDENT)
    data = reminders()
    assert not [row for row in data["active"] if row["kind"] == "ACTIVITY_DUE"] and data["counts"]["ACTIVITY_DUE"] == 0
    client.put("/me/reminder-preferences", json={"enabled_kinds": {"ACTIVITY_DUE": True}}, headers=STUDENT)
    assert item["reminder_id"] in {row["reminder_id"] for row in reminders()["active"]}


def test_a_muted_review_reminder_does_not_return_once_the_review_is_no_longer_waiting(clock):
    item = due_review(clock)
    client.put("/me/reminder-preferences", json={"enabled_kinds": {"MINI_TEST": False}}, headers=STUDENT)
    assert not reminders()["active"]
    client.patch("/activities/ACT_SQL_01/schedule", json={"action": "CANCEL"}, headers=STUDENT)
    client.put("/me/reminder-preferences", json={"enabled_kinds": {"MINI_TEST": True}}, headers=STUDENT)
    assert item["reminder_id"] not in {row["reminder_id"] for row in reminders()["active"]}


def test_a_reminder_marked_seen_cannot_be_snoozed_back_to_life(clock):
    item = overdue(clock)
    path = f"/me/reminders/{item['reminder_id']}"
    assert client.post(f"{path}/dismiss", headers=STUDENT).status_code == 200
    assert client.post(f"{path}/snooze", json={"days": 1}, headers=STUDENT).status_code == 409
    assert client.post(f"{path}/dismiss", headers=STUDENT).status_code == 409
    assert client.post(f"{path}/resume", headers=STUDENT).status_code == 409
    clock.advance(days=3)
    assert item["reminder_id"] not in {row["reminder_id"] for row in reminders()["active"]}


# --- New actions ---

def test_a_snoozed_reminder_can_be_brought_back_at_once(clock):
    item = overdue(clock)
    path = f"/me/reminders/{item['reminder_id']}"
    assert client.post(f"{path}/resume", headers=STUDENT).status_code == 409  # not snoozed yet
    client.post(f"{path}/snooze", json={"days": 7}, headers=STUDENT)
    data = reminders()
    assert [row["reminder_id"] for row in data["snoozed"]] == [item["reminder_id"]] and data["unread_count"] == 0
    assert client.post(f"{path}/resume", headers=STUDENT).json() == {"reminder_id": item["reminder_id"], "status": "ACTIVE"}
    data = reminders()
    assert not data["snoozed"] and item["reminder_id"] in {row["reminder_id"] for row in data["active"]}


def test_mark_all_seen_keeps_a_due_review_test(clock):
    review = due_review(clock)
    late = overdue(clock, days=3)
    data = reminders()
    assert {review["reminder_id"], late["reminder_id"]} <= {row["reminder_id"] for row in data["active"]}
    done = client.post("/me/reminders/dismiss-all", headers=STUDENT).json()["dismissed"]
    assert done == data["unread_count"] - data["counts"]["MINI_TEST"]
    left = reminders()["active"]
    assert [row["kind"] for row in left] == ["MINI_TEST"] and left[0]["can_dismiss"] is False


def test_the_list_puts_overdue_first_and_counts_each_kind(clock):
    due_review(clock)
    overdue(clock, days=3)
    data = reminders()
    states = [row["state"] for row in data["active"]]
    assert states[0] == "OVERDUE" and states == sorted(states, key=["OVERDUE", "MINI_TEST", "DUE_SOON", "UNSCHEDULED"].index)
    assert sum(data["counts"].values()) == data["unread_count"] == len(data["active"])
    assert data["overdue_count"] == states.count("OVERDUE")
    review = next(row for row in data["active"] if row["kind"] == "MINI_TEST")
    assert review["activity_title"] and review["payload"]["micro_id"]


def test_reminder_actions_belong_to_the_owner_only(clock):
    item = overdue(clock)
    path = f"/me/reminders/{item['reminder_id']}"
    assert client.post(f"{path}/snooze", json={"days": 1}, headers=STUDENT_2).status_code == 404
    assert client.post(f"{path}/resume", headers=STUDENT_2).status_code == 404
    assert client.post("/me/reminders/dismiss-all", headers=STUDENT_2).json() == {"dismissed": 0}
    assert item["reminder_id"] in {row["reminder_id"] for row in reminders()["active"]}
    assert reminders(STUDENT_2)["active"] == []


def test_an_older_reminder_with_an_iso_date_is_shown_day_first(clock):
    item = overdue(clock)
    store.db.execute("UPDATE reminder_jobs SET body = 'Dự kiến hoàn thành trước 2026-11-15.' WHERE reminder_id = ?", (item["reminder_id"],))
    shown = next(row for row in reminders()["active"] if row["reminder_id"] == item["reminder_id"])
    assert shown["body"] == "Dự kiến hoàn thành trước 15/11/2026."
