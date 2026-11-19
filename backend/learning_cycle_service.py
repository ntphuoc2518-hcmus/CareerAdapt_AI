"""Review cycles, reminders and mini-tests (F10, F20, F21).

The scan in ``run_scan`` is the only code that creates reminders and due mini-tests. Unique keys in
the database make it safe to run it as often as needed: a due date gives exactly one reminder and
one mini-test, however many times the scan runs or however many requests race.
"""
from __future__ import annotations

import json
import random
import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend import assessment_policy as policy
from backend.clock import utcnow
from backend.database import dumps
from backend.store import store

ALLOWED_PRESET_CYCLES = (3, 7, 14, 30)
MIN_CYCLE_DAYS = 1
MAX_CYCLE_DAYS = 90
DEFAULT_CYCLE_DAYS = 7
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
REMINDER_LOCAL_HOUR = 8
MINI_TEST_ITEMS = 4
MINI_TEST_MINUTES = 8
PASS_THRESHOLD = policy.MINI_TEST_PASS_SCORE
RECENT_MINI_TESTS_EXCLUDED = 3
DUE_SOON_DAYS = 2
REMINDER_KINDS = ("MINI_TEST", "ACTIVITY_DUE", "SCHEDULE")


def _user(user_id: uuid.UUID) -> str:
    return str(user_id)


def get_preferences(user_id: uuid.UUID) -> dict:
    row = store.db.one("SELECT payload FROM reminder_preferences WHERE user_id = ?", (_user(user_id),))
    defaults = {"timezone": DEFAULT_TIMEZONE, "default_cycle_days": DEFAULT_CYCLE_DAYS, "enabled_kinds": {kind: True for kind in REMINDER_KINDS}}
    return {**defaults, **json.loads(row["payload"])} if row else defaults


def save_preferences(user_id: uuid.UUID, preferences: dict) -> dict:
    store.db.execute(
        "INSERT INTO reminder_preferences(user_id, payload, updated_at) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at",
        (_user(user_id), dumps(preferences), utcnow().isoformat()),
    )
    return preferences


def zone_of(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("Múi giờ không hợp lệ.") from error


def local_today(preferences: dict) -> date:
    return utcnow().astimezone(zone_of(preferences["timezone"])).date()


def compute_due_at(anchor: date, cycle_days: int, timezone_name: str) -> datetime:
    """Local morning of the day `cycle_days` after the anchor, stored as UTC."""
    local = datetime.combine(anchor + timedelta(days=cycle_days), time(REMINDER_LOCAL_HOUR), tzinfo=zone_of(timezone_name))
    return local.astimezone(timezone.utc)


def validate_cycle(cycle_days: int) -> None:
    if not MIN_CYCLE_DAYS <= cycle_days <= MAX_CYCLE_DAYS:
        raise ValueError(f"Chu kỳ phải từ {MIN_CYCLE_DAYS} đến {MAX_CYCLE_DAYS} ngày.")


def _checkin_view(row: dict) -> dict:
    activity = store.get_activity(row["activity_id"]) or {}
    micro = store.db.one("SELECT micro_id, status FROM micro_assessments WHERE checkin_id = ? ORDER BY created_at DESC LIMIT 1", (row["checkin_id"],))
    return {**row, "activity_title": activity.get("title", row["activity_id"]), "micro_id": (micro or {}).get("micro_id"), "micro_status": (micro or {}).get("status")}


def active_checkin(user_id: uuid.UUID, activity_id: str) -> Optional[dict]:
    return store.db.one(
        "SELECT * FROM learning_checkins WHERE user_id = ? AND activity_id = ? AND status IN ('SCHEDULED', 'DUE', 'SNOOZED') ORDER BY created_at DESC LIMIT 1",
        (_user(user_id), activity_id),
    )


def _supersede(checkin: dict, reason_id: Optional[str]) -> None:
    """Retire a check-in and everything issued for it, so the old schedule sends nothing."""
    now = utcnow().isoformat()
    store.db.execute("UPDATE learning_checkins SET status = 'SUPERSEDED', superseded_by = ?, updated_at = ? WHERE checkin_id = ?", (reason_id, now, checkin["checkin_id"]))
    store.db.execute("UPDATE reminder_jobs SET status = 'SUPERSEDED', updated_at = ? WHERE ref_id = ? AND status IN ('ACTIVE', 'SNOOZED')", (now, checkin["checkin_id"]))
    store.db.execute("UPDATE micro_assessments SET status = 'CANCELLED' WHERE checkin_id = ? AND status = 'PENDING'", (checkin["checkin_id"],))


def create_checkin(user_id: uuid.UUID, activity: dict, cycle_days: int, anchor: date, roadmap_version: Optional[int], timezone_name: str) -> dict:
    validate_cycle(cycle_days)
    checkin_id = str(uuid.uuid4())
    now = utcnow().isoformat()
    due = compute_due_at(anchor, cycle_days, timezone_name)
    with store.db.transaction():
        previous = active_checkin(user_id, activity["activity_id"])
        if previous:
            _supersede(previous, checkin_id)
        store.db.execute(
            """INSERT INTO learning_checkins(checkin_id, user_id, activity_id, skill_code, roadmap_version, cycle_days, anchor_date, due_at, timezone, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'SCHEDULED', ?, ?)""",
            (checkin_id, _user(user_id), activity["activity_id"], activity.get("target_skill"), roadmap_version, cycle_days, anchor.isoformat(), due.isoformat(), timezone_name, now, now),
        )
    return _checkin_view(store.db.one("SELECT * FROM learning_checkins WHERE checkin_id = ?", (checkin_id,)))


def ensure_checkin(user_id: uuid.UUID, activity: dict, roadmap_version: Optional[int]) -> dict:
    """A completed activity gets a review date from the learner's default cycle unless one exists."""
    existing = active_checkin(user_id, activity["activity_id"])
    if existing:
        return _checkin_view(existing)
    preferences = get_preferences(user_id)
    return create_checkin(user_id, activity, int(preferences["default_cycle_days"]), local_today(preferences), roadmap_version, preferences["timezone"])


def _insert_reminder(user_id: str, kind: str, ref_id: Optional[str], dedupe_key: str, title: str, body: str, payload: dict, when: str) -> bool:
    now = utcnow().isoformat()
    return store.db.execute(
        """INSERT OR IGNORE INTO reminder_jobs(reminder_id, user_id, kind, ref_id, dedupe_key, scheduled_at, sent_at, status, title, body, payload, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?)""",
        (str(uuid.uuid4()), user_id, kind, ref_id, dedupe_key, when, now, title, body, dumps(payload), now),
    ).rowcount > 0


def select_micro_items(skill_code: str, max_level: int, excluded: set[str], seed: Optional[int] = None) -> list[dict]:
    """Pick 3-5 active questions for the skill, avoiding items the learner saw recently.

    The level estimate climbs from level 1 and stops at the first level not tested, so the form
    holds a question of every level, repeating a recent one only when a level has no fresh one.
    """
    rng = random.Random(seed)
    pool = [item for item in store.question_items if item["skill_code"] == skill_code and item.get("status", "ACTIVE") == "ACTIVE" and int(item["level"]) <= max(max_level, 1)]
    rng.shuffle(pool)
    pool.sort(key=lambda item: item["item_id"] in excluded)  # fresh items first
    fresh = [item for item in pool if item["item_id"] not in excluded]
    candidates = fresh if len(fresh) >= 3 else pool
    if len(candidates) < 3:
        return []
    levels = sorted({int(item["level"]) for item in pool})
    chosen = [next(item for item in pool if int(item["level"]) == level) for level in levels]
    picked = {item["item_id"] for item in chosen}
    # Cover the highest level studied: the mini-test must be able to show the learning outcome.
    rest = [item for item in candidates if item["item_id"] not in picked]
    rest.sort(key=lambda item: int(item["level"]) != levels[-1])
    chosen += rest[: MINI_TEST_ITEMS - len(chosen)]
    rng.shuffle(chosen)
    return chosen


def _recent_items(user_id: str, skill_code: str) -> set[str]:
    rows = store.db.query(
        "SELECT payload FROM micro_assessments WHERE user_id = ? AND skill_code = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, skill_code, RECENT_MINI_TESTS_EXCLUDED),
    )
    return {item["item_id"] for row in rows for item in json.loads(row["payload"]).get("items", [])}


def _issue_mini_test(checkin: dict) -> Optional[str]:
    activity = store.get_activity(checkin["activity_id"]) or {}
    items = select_micro_items(checkin["skill_code"], int(activity.get("target_level", 2)), _recent_items(checkin["user_id"], checkin["skill_code"]))
    status = "PENDING" if items else "UNAVAILABLE"
    micro_id = str(uuid.uuid4())
    orders = {}
    for item in items:
        order = [option["id"] for option in item.get("options", [])]
        random.shuffle(order)
        orders[item["item_id"]] = order
    payload = {"items": items, "option_orders": orders, "time_limit_minutes": MINI_TEST_MINUTES, "pass_threshold": PASS_THRESHOLD,
               "activity_title": activity.get("title"), "resource_ids": activity.get("resource_ids", []), "roadmap_version": checkin["roadmap_version"]}
    inserted = store.db.execute(
        """INSERT OR IGNORE INTO micro_assessments(micro_id, user_id, checkin_id, due_at, skill_code, activity_id, status, bank_version, payload, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (micro_id, checkin["user_id"], checkin["checkin_id"], checkin["due_at"], checkin["skill_code"], checkin["activity_id"], status, store.question_bank_version, dumps(payload), utcnow().isoformat()),
    ).rowcount
    return micro_id if inserted else None


def run_scan(user_id: Optional[uuid.UUID] = None) -> dict:
    """Turn due events into reminders and mini-tests. Safe to repeat; never duplicates anything."""
    now = utcnow()
    now_iso = now.isoformat()
    scope = "" if user_id is None else " AND user_id = ?"
    parameters: tuple[Any, ...] = () if user_id is None else (_user(user_id),)
    created = {"reminders": 0, "mini_tests": 0}
    with store.db.transaction():
        # A snoozed reminder returns as the same row, so the learner never sees a second copy.
        store.db.execute(f"UPDATE reminder_jobs SET status = 'ACTIVE', snooze_until = NULL, updated_at = ? WHERE status = 'SNOOZED' AND snooze_until <= ?{scope}", (now_iso, now_iso, *parameters))
        store.db.execute(f"UPDATE learning_checkins SET status = 'DUE', updated_at = ? WHERE status = 'SNOOZED' AND due_at <= ?{scope}", (now_iso, now_iso, *parameters))
        due = store.db.query(f"SELECT * FROM learning_checkins WHERE status = 'SCHEDULED' AND due_at <= ?{scope}", (now_iso, *parameters))
        for checkin in due:
            owner = uuid.UUID(checkin["user_id"])
            preferences = get_preferences(owner)
            micro_id = _issue_mini_test(checkin)
            if micro_id:
                created["mini_tests"] += 1
            store.db.execute("UPDATE learning_checkins SET status = 'DUE', updated_at = ? WHERE checkin_id = ?", (now_iso, checkin["checkin_id"]))
            title = (store.get_activity(checkin["activity_id"]) or {}).get("title", checkin["activity_id"])
            if preferences["enabled_kinds"].get("MINI_TEST", True):
                created["reminders"] += int(_insert_reminder(
                    checkin["user_id"], "MINI_TEST", checkin["checkin_id"], f"MINI_TEST:{checkin['checkin_id']}:{checkin['due_at']}",
                    f"Đến hạn mini-test: {title}", "Bài kiểm tra ngắn khoảng 5-10 phút về nội dung bạn vừa học.",
                    {"activity_id": checkin["activity_id"], "skill_code": checkin["skill_code"], "micro_id": micro_id, "state": "MINI_TEST", "activity_title": title}, checkin["due_at"],
                ))
        created["reminders"] += _scan_activity_deadlines(now, user_id)
    return created


def _retire_stale(owner: uuid.UUID, valid: set[str], now_iso: str) -> None:
    """Close plan reminders that no longer describe the plan: the lesson was finished or re-planned, a "due soon"
    note whose date has passed (its "overdue" twin replaces it), a new roadmap version, or a kind turned off."""
    rows = store.db.query("SELECT reminder_id, dedupe_key FROM reminder_jobs WHERE user_id = ? AND kind IN ('ACTIVITY_DUE', 'SCHEDULE') AND status IN ('ACTIVE', 'SNOOZED')", (_user(owner),))
    for row in rows:
        if row["dedupe_key"] not in valid:
            store.db.execute("UPDATE reminder_jobs SET status = 'SUPERSEDED', updated_at = ? WHERE reminder_id = ?", (now_iso, row["reminder_id"]))


def apply_kind_preferences(user_id: uuid.UUID, preferences: dict) -> None:
    """Turning a kind off hides the reminders of that kind that are already showing (status MUTED); turning it
    back on shows them again if they still apply. The next scan retires any that went stale meanwhile."""
    now, user = utcnow().isoformat(), _user(user_id)
    for kind in REMINDER_KINDS:
        if not preferences["enabled_kinds"].get(kind, True):
            store.db.execute("UPDATE reminder_jobs SET status = 'MUTED', snooze_until = NULL, updated_at = ? WHERE user_id = ? AND kind = ? AND status IN ('ACTIVE', 'SNOOZED')", (now, user, kind))
        elif kind == "MINI_TEST":
            # Only while the review is still waiting: a finished or re-planned one must not come back.
            store.db.execute("""UPDATE reminder_jobs SET status = 'ACTIVE', updated_at = ? WHERE user_id = ? AND kind = 'MINI_TEST' AND status = 'MUTED'
                                AND ref_id IN (SELECT checkin_id FROM learning_checkins WHERE status IN ('DUE', 'SNOOZED'))""", (now, user))
        else:
            store.db.execute("UPDATE reminder_jobs SET status = 'ACTIVE', updated_at = ? WHERE user_id = ? AND kind = ? AND status = 'MUTED'", (now, user, kind))


def _scan_activity_deadlines(now: datetime, user_id: Optional[uuid.UUID]) -> int:
    count = 0
    owners = [user_id] if user_id else list({*store.roadmaps, *(uuid.UUID(row["user_id"]) for row in store.db.query(
        "SELECT DISTINCT user_id FROM reminder_jobs WHERE kind IN ('ACTIVITY_DUE', 'SCHEDULE') AND status IN ('ACTIVE', 'SNOOZED')"))})
    for owner in owners:
        roadmap = store.roadmaps.get(owner) or {}
        valid: set[str] = set()
        if not roadmap.get("activity_plan"):
            _retire_stale(owner, valid, now.isoformat())
            continue
        preferences = get_preferences(owner)
        today = now.astimezone(zone_of(preferences["timezone"])).date()
        version = roadmap.get("roadmap_version")
        progress = roadmap.get("activity_progress", {})
        for activity_id, plan in roadmap["activity_plan"].items():
            if plan.get("kind") != "LEARNING" or not preferences["enabled_kinds"].get("ACTIVITY_DUE", True):
                continue
            if (progress.get(activity_id) or {}).get("status") == "COMPLETED":
                continue
            end = date.fromisoformat(plan["planned_end"])
            title = (store.get_activity(activity_id) or {}).get("title", activity_id)
            payload = {"activity_id": activity_id, "planned_end": plan["planned_end"], "activity_title": title}
            if today > end:
                key = f"OVERDUE:{activity_id}:{plan['planned_end']}:{version}"
                count += int(_insert_reminder(_user(owner), "ACTIVITY_DUE", activity_id, key,
                                              f"Quá hạn dự kiến: {title}", "Trễ hạn chỉ là trạng thái kế hoạch, không phải đánh giá năng lực. Bạn có thể cập nhật tiến độ hoặc lập lại lịch.",
                                              {**payload, "state": "OVERDUE"}, now.isoformat()))
                valid.add(key)
            elif (end - today).days <= DUE_SOON_DAYS:
                key = f"DUE_SOON:{activity_id}:{plan['planned_end']}:{version}"
                count += int(_insert_reminder(_user(owner), "ACTIVITY_DUE", activity_id, key,
                                              f"Sắp đến hạn: {title}", f"Dự kiến hoàn thành trước {end.strftime('%d/%m/%Y')}.",
                                              {**payload, "state": "DUE_SOON"}, now.isoformat()))
                valid.add(key)
        unscheduled = [item for item in (roadmap.get("schedule") or {}).get("unscheduled_activities", []) if item.get("kind") != "JD_REQUIREMENT"]
        if unscheduled and preferences["enabled_kinds"].get("SCHEDULE", True):
            count += int(_insert_reminder(_user(owner), "SCHEDULE", str(version), f"UNSCHEDULED:{version}",
                                          f"Lịch hiện tại còn {len(unscheduled)} hoạt động chưa xếp được", "Xem lý do ở trang Lộ trình và cân nhắc kéo dài thời hạn hoặc đổi mục tiêu.",
                                          {"roadmap_version": version, "state": "UNSCHEDULED"}, now.isoformat()))
            valid.add(f"UNSCHEDULED:{version}")
        _retire_stale(owner, valid, now.isoformat())
    return count


def reminder_view(row: dict, today: date) -> dict:
    """A reminder as the page shows it. ``state`` and ``days`` are worked out here so the page never computes dates:
    days < 0 is that many days past the planned date, days >= 0 is that many days left."""
    payload = json.loads(row["payload"] or "{}") if isinstance(row.get("payload"), str) or row.get("payload") is None else row["payload"]
    state = payload.get("state") or {"MINI_TEST": "MINI_TEST", "SCHEDULE": "UNSCHEDULED"}.get(row["kind"]) or row["dedupe_key"].split(":", 1)[0]
    days = None
    if row["kind"] == "ACTIVITY_DUE" and payload.get("planned_end"):
        days = (date.fromisoformat(payload["planned_end"]) - today).days
        # The stored row keeps the state it was made with; the date decides what is true now.
        state = "OVERDUE" if days < 0 else "DUE_SOON"
    elif row["kind"] == "MINI_TEST":
        days = -max(0, (today - datetime.fromisoformat(row["scheduled_at"]).date()).days)
    activity_id = payload.get("activity_id")
    title = payload.get("activity_title") or ((store.get_activity(activity_id) or {}).get("title") if activity_id else None)
    # Reminders written before 5.29 carry the date as 2026-11-15; show it day first like everywhere else.
    body = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", r"\3/\2/\1", row["body"] or "")
    return {**{key: row[key] for key in ("reminder_id", "kind", "ref_id", "status", "title", "scheduled_at", "snooze_until", "updated_at")},
            "body": body, "payload": payload, "state": state, "days": days, "activity_id": activity_id, "activity_title": title, "can_dismiss": row["kind"] != "MINI_TEST"}


def resolve_activity_reminders(user_id: uuid.UUID, activity_id: str) -> None:
    store.db.execute(
        "UPDATE reminder_jobs SET status = 'DONE', updated_at = ? WHERE user_id = ? AND kind = 'ACTIVITY_DUE' AND ref_id = ? AND status IN ('ACTIVE', 'SNOOZED')",
        (utcnow().isoformat(), _user(user_id), activity_id),
    )
