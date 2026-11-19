"""Learning Roadmap 2.0: study sessions, the review cycle chosen at the first start, and the lesson view.

Study time is measured on the server. The browser only reports a heartbeat while the lesson page is
open; the time counted is always computed from server timestamps, so a refresh, a second tab or a lost
connection can never add time twice. Time is learning progress only: it never sets a level or a score.

Each lesson has two independent states:
- learning_state: NOT_STARTED, STUDYING, PAUSED, PENDING_CHECK, NEEDS_REVIEW, COMPLETED
- review_state:   NONE, SCHEDULED, DUE, PASSED, RELEARN
COMPLETED means the lesson completion check was passed; marking a lesson as studied never does that.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status

from backend.catalog import get_resource, is_usable
from backend.clock import utcnow
from backend.learning_cycle_service import MAX_CYCLE_DAYS, MIN_CYCLE_DAYS, run_scan
from backend.lesson_checks import GRADED, LESSON_CHECK_KIND, check_summary, confirmable_level, latest_graded, lesson_checks, level_confirmed, retry_available_at
from backend.store import store

REVIEW_PRESETS = (1, 3, 7, 14)
HEARTBEAT_SECONDS = 60
# No heartbeat for this long means the page is gone (closed, offline, asleep): the session pauses at the last heartbeat.
STALE_SECONDS = 300
# A single uninterrupted stretch never counts for more than this.
MAX_SEGMENT_SECONDS = 4 * 3600
OPEN = ("RUNNING", "PAUSED")
LEARNING_STATES = ("NOT_STARTED", "STUDYING", "PAUSED", "PENDING_CHECK", "NEEDS_REVIEW", "COMPLETED")
REVIEW_STATES = ("NONE", "SCHEDULED", "DUE", "PASSED", "RELEARN")


def _now() -> datetime:
    return utcnow()


def _parse(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _key(user_id: uuid.UUID) -> str:
    return str(user_id)


# ---------------------------------------------------------------- review cycle chosen at the first start
def lesson_plan(user_id: uuid.UUID, activity_id: str) -> Optional[dict]:
    return store.db.one("SELECT * FROM lesson_plans WHERE user_id = ? AND activity_id = ? AND archived_by_run IS NULL", (_key(user_id), activity_id))


def validate_review_cycle(days: Optional[int]) -> int:
    if days is None:
        raise HTTPException(status_code=422, detail="Hãy chọn thời gian kiểm tra lại trước khi bắt đầu học bài này.")
    if not MIN_CYCLE_DAYS <= int(days) <= MAX_CYCLE_DAYS:
        raise HTTPException(status_code=422, detail=f"Thời gian kiểm tra lại phải từ {MIN_CYCLE_DAYS} đến {MAX_CYCLE_DAYS} ngày.")
    return int(days)


def _ensure_plan(user_id: uuid.UUID, activity_id: str, days: Optional[int]) -> dict:
    """The cycle is chosen once. A later start never changes it, whatever it sends."""
    existing = lesson_plan(user_id, activity_id)
    if existing:
        return existing
    cycle = validate_review_cycle(days)
    store.db.execute(
        "INSERT OR IGNORE INTO lesson_plans(plan_id, user_id, activity_id, review_cycle_days, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), _key(user_id), activity_id, cycle, _now().isoformat()),
    )
    return lesson_plan(user_id, activity_id)


# ---------------------------------------------------------------- study sessions
def _segment_seconds(row: dict, until: datetime) -> int:
    start = _parse(row["segment_started_at"])
    if not start:
        return 0
    return max(0, min(int((until - start).total_seconds()), MAX_SEGMENT_SECONDS))


def _settle(row: Optional[dict]) -> Optional[dict]:
    """Pause a running session whose page went silent, or that ran past the segment limit.

    Time counts only up to the last heartbeat (or the limit), so a closed laptop adds nothing.
    """
    if not row or row["status"] != "RUNNING":
        return row
    now = _now()
    heartbeat = _parse(row["last_heartbeat_at"]) or _parse(row["segment_started_at"])
    start = _parse(row["segment_started_at"])
    reason = None
    until = now
    if (now - heartbeat).total_seconds() > STALE_SECONDS:
        reason, until = "INTERRUPTED", heartbeat
    elif start and (now - start).total_seconds() > MAX_SEGMENT_SECONDS:
        reason, until = "LIMIT", start + timedelta(seconds=MAX_SEGMENT_SECONDS)
    if not reason:
        return row
    store.db.execute(
        "UPDATE study_sessions SET status = 'PAUSED', accumulated_seconds = accumulated_seconds + ?, segment_started_at = NULL, paused_at = ?, pause_reason = ?, updated_at = ? "
        "WHERE session_id = ? AND status = 'RUNNING'",
        (_segment_seconds(row, until), until.isoformat(), reason, now.isoformat(), row["session_id"]),
    )
    return _session(row["session_id"])


def _session(session_id: str) -> Optional[dict]:
    return store.db.one("SELECT * FROM study_sessions WHERE session_id = ?", (session_id,))


def elapsed_seconds(row: dict) -> int:
    total = int(row["accumulated_seconds"] or 0)
    if row["status"] == "RUNNING":
        total += _segment_seconds(row, _now())
    return total


def session_view(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    activity = store.get_activity(row["activity_id"]) or {}
    return {
        "session_id": row["session_id"], "activity_id": row["activity_id"], "activity_title": activity.get("title", row["activity_id"]), "status": row["status"],
        "started_at": row["started_at"], "paused_at": row["paused_at"], "ended_at": row["ended_at"], "pause_reason": row["pause_reason"], "end_reason": row["end_reason"],
        "elapsed_seconds": elapsed_seconds(row), "server_time": _now().isoformat(), "heartbeat_seconds": HEARTBEAT_SECONDS,
    }


def open_sessions(user_id: uuid.UUID) -> list[dict]:
    rows = store.db.query("SELECT * FROM study_sessions WHERE user_id = ? AND status IN ('RUNNING', 'PAUSED') AND archived_by_run IS NULL", (_key(user_id),))
    return [_settle(row) for row in rows]


def current_session(user_id: uuid.UUID) -> Optional[dict]:
    """The running session, else the most recently paused one."""
    rows = open_sessions(user_id)
    running = [row for row in rows if row["status"] == "RUNNING"]
    if running:
        return running[0]
    return max(rows, key=lambda row: row["updated_at"]) if rows else None


def _owned(user_id: uuid.UUID, session_id: str) -> dict:
    row = _session(session_id)
    if not row or row["user_id"] != _key(user_id) or row["archived_by_run"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiên học.")
    return _settle(row)


def start_session(user_id: uuid.UUID, activity: dict, roadmap_version: Optional[int], review_cycle_days: Optional[int], switch: bool) -> dict:
    """Start or resume studying a lesson. Starting again from another tab joins the same session."""
    activity_id = activity["activity_id"]
    for row in open_sessions(user_id):
        if row["activity_id"] == activity_id:
            return resume_session(user_id, row["session_id"]) if row["status"] == "PAUSED" else row
        if row["status"] == "RUNNING":
            if not switch:
                title = (store.get_activity(row["activity_id"]) or {}).get("title", row["activity_id"])
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Bạn đang bấm giờ cho bài “{title}”. Hãy tạm dừng bài đó trước, hoặc chọn chuyển sang bài này.")
            pause_session(user_id, row["session_id"])
    _ensure_plan(user_id, activity_id, review_cycle_days)
    now = _now().isoformat()
    session_id = str(uuid.uuid4())
    try:
        store.db.execute(
            "INSERT INTO study_sessions(session_id, user_id, activity_id, status, started_at, segment_started_at, last_heartbeat_at, accumulated_seconds, roadmap_version, updated_at) "
            "VALUES (?, ?, ?, 'RUNNING', ?, ?, ?, 0, ?, ?)",
            (session_id, _key(user_id), activity_id, now, now, now, roadmap_version, now),
        )
    except Exception as error:  # A second tab won the race: the unique index allows one running session.
        if "UNIQUE" not in str(error):
            raise
        existing = current_session(user_id)
        if existing and existing["activity_id"] == activity_id:
            return existing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Một phiên học khác vừa được bắt đầu. Hãy tải lại trang.")
    store.add_history_event(user_id, "STUDY_STARTED", f"Bắt đầu học: {activity.get('title', activity_id)}", meta={"activity_id": activity_id, "session_id": session_id})
    return _session(session_id)


def pause_session(user_id: uuid.UUID, session_id: str) -> dict:
    row = _owned(user_id, session_id)
    if row["status"] == "RUNNING":
        now = _now()
        store.db.execute(
            "UPDATE study_sessions SET status = 'PAUSED', accumulated_seconds = accumulated_seconds + ?, segment_started_at = NULL, paused_at = ?, pause_reason = 'USER', updated_at = ? "
            "WHERE session_id = ? AND status = 'RUNNING'",
            (_segment_seconds(row, now), now.isoformat(), now.isoformat(), session_id),
        )
    elif row["status"] == "ENDED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phiên học này đã kết thúc.")
    return _session(session_id)


def resume_session(user_id: uuid.UUID, session_id: str) -> dict:
    row = _owned(user_id, session_id)
    if row["status"] == "ENDED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phiên học này đã kết thúc. Hãy bắt đầu phiên mới.")
    if row["status"] == "PAUSED":
        running = next((item for item in open_sessions(user_id) if item["status"] == "RUNNING" and item["session_id"] != session_id), None)
        if running:
            title = (store.get_activity(running["activity_id"]) or {}).get("title", running["activity_id"])
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Bạn đang bấm giờ cho bài “{title}”. Hãy tạm dừng bài đó trước.")
        now = _now().isoformat()
        try:
            store.db.execute(
                "UPDATE study_sessions SET status = 'RUNNING', segment_started_at = ?, last_heartbeat_at = ?, paused_at = NULL, pause_reason = NULL, updated_at = ? "
                "WHERE session_id = ? AND status = 'PAUSED'",
                (now, now, now, session_id),
            )
        except Exception as error:
            if "UNIQUE" not in str(error):
                raise
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Một phiên học khác đang chạy. Hãy tải lại trang.")
    return _session(session_id)


def heartbeat(user_id: uuid.UUID, session_id: str) -> dict:
    """Keep a running session alive. A session that already paused stays paused: the learner resumes it."""
    row = _owned(user_id, session_id)
    if row["status"] == "RUNNING":
        now = _now().isoformat()
        store.db.execute("UPDATE study_sessions SET last_heartbeat_at = ?, updated_at = ? WHERE session_id = ? AND status = 'RUNNING'", (now, now, session_id))
    return _session(session_id)


def end_session(user_id: uuid.UUID, session_id: str, reason: str = "USER") -> dict:
    row = _owned(user_id, session_id)
    if row["status"] != "ENDED":
        now = _now()
        extra = _segment_seconds(row, now) if row["status"] == "RUNNING" else 0
        store.db.execute(
            "UPDATE study_sessions SET status = 'ENDED', accumulated_seconds = accumulated_seconds + ?, segment_started_at = NULL, ended_at = ?, end_reason = ?, updated_at = ? "
            "WHERE session_id = ? AND status IN ('RUNNING', 'PAUSED')",
            (extra, now.isoformat(), reason, now.isoformat(), session_id),
        )
        ended = _session(session_id)
        activity = store.get_activity(row["activity_id"]) or {}
        store.add_history_event(user_id, "STUDY_ENDED", f"Kết thúc phiên học {activity.get('title', row['activity_id'])}: {round(ended['accumulated_seconds'] / 60)} phút",
                                meta={"activity_id": row["activity_id"], "session_id": session_id, "seconds": ended["accumulated_seconds"]})
    return _session(session_id)


def end_open_session_for(user_id: uuid.UUID, activity_id: str, reason: str) -> None:
    """Taking a test is not study time: an open session of that lesson ends first."""
    for row in open_sessions(user_id):
        if row["activity_id"] == activity_id:
            end_session(user_id, row["session_id"], reason)


def study_seconds(user_id: uuid.UUID) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in store.db.query("SELECT * FROM study_sessions WHERE user_id = ? AND archived_by_run IS NULL", (_key(user_id),)):
        row = _settle(row) if row["status"] == "RUNNING" else row
        totals[row["activity_id"]] = totals.get(row["activity_id"], 0) + elapsed_seconds(row)
    return totals


def session_history(user_id: uuid.UUID, activity_id: str, limit: int = 20) -> list[dict]:
    rows = store.db.query("SELECT * FROM study_sessions WHERE user_id = ? AND activity_id = ? AND archived_by_run IS NULL ORDER BY started_at DESC LIMIT ?", (_key(user_id), activity_id, limit))
    return [session_view(_settle(row)) for row in rows]


# ---------------------------------------------------------------- reviews
def _review_tests(user_id: uuid.UUID) -> dict[str, list[dict]]:
    rows = store.db.query(
        "SELECT * FROM micro_assessments WHERE user_id = ? AND status NOT IN ('ARCHIVED') AND COALESCE(json_extract(payload, '$.kind'), 'MINI_TEST') != ? ORDER BY created_at DESC, rowid DESC",
        (_key(user_id), LESSON_CHECK_KIND),
    )
    found: dict[str, list[dict]] = {}
    for row in rows:
        found.setdefault(row["activity_id"], []).append({**row, "payload": json.loads(row["payload"])})
    return found


def _active_checkins(user_id: uuid.UUID) -> dict[str, dict]:
    rows = store.db.query("SELECT * FROM learning_checkins WHERE user_id = ? AND status IN ('SCHEDULED', 'DUE', 'SNOOZED') ORDER BY created_at DESC", (_key(user_id),))
    found: dict[str, dict] = {}
    for row in rows:
        found.setdefault(row["activity_id"], row)
    return found


def review_summary(row: dict) -> dict:
    result = row["payload"].get("result") or {}
    return {"micro_id": row["micro_id"], "status": row["status"], "due_at": row["due_at"], "submitted_at": row["submitted_at"], "score": result.get("score"),
            "weak_topics": result.get("weak_topics", []), "pass_threshold": row["payload"].get("pass_threshold")}


def _review_state(checkin: Optional[dict], tests: list[dict]) -> dict:
    graded = [row for row in tests if row["status"] in GRADED]
    pending = next((row for row in tests if row["status"] == "PENDING" and checkin and row["checkin_id"] == checkin["checkin_id"]), None)
    if checkin:
        state = "DUE" if checkin["status"] == "DUE" else "SCHEDULED"
        return {"review_state": state, "review_due_at": checkin["due_at"], "review_cycle_days": checkin["cycle_days"], "review_micro_id": pending["micro_id"] if pending else None}
    if graded:
        return {"review_state": "PASSED" if graded[0]["status"] == "PASSED" else "RELEARN", "review_due_at": None, "review_micro_id": None}
    return {"review_state": "NONE", "review_due_at": None, "review_micro_id": None}


# ---------------------------------------------------------------- lesson state
def _learning_state(progress: Optional[dict], deciding: Optional[dict], session: Optional[dict], seconds: int, confirmed: bool = True) -> str:
    if deciding and deciding["status"] == "PASSED":
        # Passed, but the skill is still below the lesson's level (old one-step rule): a confirmation check is due.
        return "COMPLETED" if confirmed else "NEEDS_REVIEW"
    if deciding and deciding["status"] == "FAILED":
        return "NEEDS_REVIEW"
    if (progress or {}).get("status") == "COMPLETED" or (deciding and deciding["status"] in ("PENDING", "UNAVAILABLE")):
        return "PENDING_CHECK"
    if session and session["status"] == "PAUSED":
        return "PAUSED"
    if session or seconds > 0 or (progress or {}).get("status") in ("IN_PROGRESS", "PAUSED"):
        return "STUDYING"
    return "NOT_STARTED"


def lesson_states(user_id: uuid.UUID) -> dict[str, dict]:
    """Both states of every learning lesson in the current roadmap, read from the stored records."""
    from backend.lesson_checks import reconfirm_levels

    reconfirm_levels(user_id)
    run_scan(user_id)
    roadmap = store.roadmaps.get(user_id) or {}
    plan = roadmap.get("activity_plan") or {}
    progress = roadmap.get("activity_progress") or {}
    checks: dict[str, list[dict]] = {}
    for row in lesson_checks(user_id):
        checks.setdefault(row["activity_id"], []).append(row)
    sessions = {row["activity_id"]: row for row in open_sessions(user_id)}
    seconds = study_seconds(user_id)
    checkins = _active_checkins(user_id)
    reviews = _review_tests(user_id)
    states = {}
    for activity_id, planned in plan.items():
        if planned.get("kind", "LEARNING") != "LEARNING":
            continue
        own = checks.get(activity_id, [])
        deciding = latest_graded(own)
        activity = store.get_activity(activity_id) or {}
        estimated = float(activity.get("estimated_hours") or 0)
        spent = seconds.get(activity_id, 0)
        plan_row = lesson_plan(user_id, activity_id)
        confirmed = level_confirmed(user_id, activity)
        state = {
            "activity_id": activity_id, "learning_state": _learning_state(progress.get(activity_id), deciding, sessions.get(activity_id), spent, confirmed),
            "level_short": bool(deciding and deciding["status"] == "PASSED" and not confirmed), "target_level": int(activity.get("target_level") or 1),
            "skill_level": ((store.get_or_create_profile(user_id).get("assessed_skills") or {}).get(activity.get("target_skill")) or {}).get("level"),
            "study_seconds": spent, "estimated_hours": estimated, "time_percent": min(100, round(100 * spent / (estimated * 3600))) if estimated else 0,
            "time_reached": bool(estimated) and spent >= estimated * 3600, "session": session_view(sessions.get(activity_id)),
            "review_cycle_days": plan_row["review_cycle_days"] if plan_row else None, "cycle_locked": bool(plan_row),
            "latest_check": check_summary(deciding), "open_check_id": next((row["micro_id"] for row in own if row["status"] == "PENDING"), None),
            "graded_attempts": len([row for row in own if row["status"] in GRADED]),
            # What the completion check can confirm (level 3 waits for the final assessment) and when a failed check may be retaken.
            "confirm_level": confirmable_level(activity),
            "retry_at": (lambda moment: moment.isoformat() if moment else None)(retry_available_at(user_id, activity_id)) if deciding and deciding["status"] == "FAILED" else None,
        }
        review = _review_state(checkins.get(activity_id), reviews.get(activity_id, []))
        # The locked cycle is the learner's choice; a legacy lesson shows the cycle of its open review.
        review["review_cycle_days"] = state["review_cycle_days"] or review.get("review_cycle_days")
        state.update(review)
        states[activity_id] = state
    return states


# ---------------------------------------------------------------- weeks and overview
def _week_state(states: list[dict]) -> str:
    learning = [item["learning_state"] for item in states]
    if not learning:
        return "ASSESSMENT"
    if all(state == "COMPLETED" for state in learning):
        return "DONE"
    if "NEEDS_REVIEW" in learning:
        return "NEEDS_REVIEW"
    if "PENDING_CHECK" in learning:
        return "PENDING_CHECK"
    if any(state != "NOT_STARTED" for state in learning):
        return "IN_PROGRESS"
    return "NOT_STARTED"


def _week(week: dict, states: dict[str, dict], today: Optional[date] = None) -> dict:
    lessons, topics = [], {}
    for item in week["activities"]:
        if item.get("kind") == "ASSESSMENT":
            continue
        activity = store.get_activity(item["activity_id"]) or {}
        state = states.get(item["activity_id"], {})
        lesson = {
            "activity_id": item["activity_id"], "title": item.get("title") or activity.get("title"), "target_skill": item.get("target_skill"), "target_level": item.get("target_level"),
            "allocated_hours": item.get("allocated_hours"), "segment": item.get("segment"), "total_segments": item.get("total_segments"), "estimated_hours": activity.get("estimated_hours"),
            **{key: state.get(key) for key in ("learning_state", "level_short", "confirm_level", "retry_at", "review_state", "review_due_at", "study_seconds", "time_percent", "session", "review_micro_id", "open_check_id", "review_cycle_days")},
        }
        lessons.append(lesson)
        topics.setdefault(item.get("target_skill"), []).append(lesson)
    distinct = list(dict.fromkeys(lesson["activity_id"] for lesson in lessons))
    unique = [states[activity_id] for activity_id in distinct if activity_id in states]
    done = sum(1 for item in unique if item["learning_state"] == "COMPLETED")
    following = next((lesson for lesson in lessons if lesson["learning_state"] != "COMPLETED"), None)
    outcomes = list(dict.fromkeys((store.get_activity(activity_id) or {}).get("learning_outcome") for activity_id in distinct))
    end = date.fromisoformat(week["start_date"]) + timedelta(days=6)
    state = _week_state(unique)
    # A week whose last day has passed with lessons still open is late: the plan no longer matches the calendar (audit B-01).
    overdue = (today - end).days if today and state not in ("DONE", "ASSESSMENT") and today > end else 0
    return {
        "week_number": week["week_number"], "start_date": week["start_date"], "end_date": (date.fromisoformat(week["start_date"]) + timedelta(days=6)).isoformat(),
        "allocated_hours": week.get("allocated_hours"), "topics": [{"skill_code": code, "lessons": items} for code, items in topics.items()],
        "lessons_total": len(distinct), "lessons_done": done, "percent": round(100 * done / len(distinct)) if distinct else 0, "state": state, "overdue_days": overdue,
        "next_lesson": {"activity_id": following["activity_id"], "title": following["title"]} if following else None,
        "objectives": [text for text in outcomes if text], "assessments": [item for item in week["activities"] if item.get("kind") == "ASSESSMENT"],
    }


def journey(user_id: uuid.UUID) -> Optional[dict]:
    """Roadmap overview: when it ends, progress, lessons waiting for a check, the next lesson and the weeks."""
    roadmap = store.roadmaps.get(user_id) or {}
    schedule = roadmap.get("schedule")
    if not schedule:
        return None
    states = lesson_states(user_id)
    from backend.learning_cycle_service import get_preferences, local_today

    today = local_today(get_preferences(user_id))
    weeks = [_week(week, states, today) for week in schedule.get("scheduled_weeks", [])]
    late = [week for week in weeks if week["overdue_days"]]
    total = len(states)
    done = sum(1 for item in states.values() if item["learning_state"] == "COMPLETED")
    waiting = [item for item in states.values() if item["review_state"] == "DUE" or item["learning_state"] in ("PENDING_CHECK", "NEEDS_REVIEW")]
    following = next((dict(lesson, week_number=week["week_number"]) for week in weeks for lesson in (item for topic in week["topics"] for item in topic["lessons"]) if lesson["learning_state"] != "COMPLETED"), None)
    from backend import final_assessment

    return {
        "roadmap_version": roadmap.get("roadmap_version"), "target": roadmap.get("target"), "start_date": roadmap.get("start_date"),
        "expected_end_date": weeks[-1]["end_date"] if weeks else None, "total_weeks": len(weeks), "weekly_hours_budget": roadmap.get("weekly_hours_budget"),
        "lessons_total": total, "lessons_done": done, "percent": round(100 * done / total) if total else 0,
        "study_seconds": sum(item["study_seconds"] for item in states.values()),
        "waiting_checks": len(waiting), "due_reviews": sum(1 for item in states.values() if item["review_state"] == "DUE"),
        "pending_completion_checks": sum(1 for item in states.values() if item["learning_state"] in ("PENDING_CHECK", "NEEDS_REVIEW")),
        "next_lesson": following, "weeks": weeks, "current_session": session_view(current_session(user_id)),
        "unscheduled": schedule.get("unscheduled_activities", []), "meets_deadline": schedule.get("meets_deadline"),
        "carried_lessons": [{"activity_id": activity_id, "title": (store.get_activity(activity_id) or {}).get("title", activity_id), "target_skill": (store.get_activity(activity_id) or {}).get("target_skill"),
                             "learning_state": states.get(activity_id, {}).get("learning_state"), "review_state": states.get(activity_id, {}).get("review_state"), "review_due_at": states.get(activity_id, {}).get("review_due_at")}
                            for activity_id, entry in (roadmap.get("activity_plan") or {}).items() if entry.get("carried_over")],
        "retired_lessons": roadmap.get("retired_lessons", []), "change_reason": roadmap.get("change_reason"), "replanned_at": roadmap.get("replanned_at"),
        "final": final_assessment.status_for(user_id, states),
        "behind": {"weeks": len(late), "days": max(week["overdue_days"] for week in late), "lessons": sum(week["lessons_total"] - week["lessons_done"] for week in late)} if late else None,
    }


def week_detail(user_id: uuid.UUID, week_number: int) -> dict:
    overview = journey(user_id)
    week = next((item for item in (overview or {}).get("weeks", []) if item["week_number"] == week_number), None)
    if not week:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không có tuần này trong lộ trình hiện tại.")
    numbers = [item["week_number"] for item in overview["weeks"]]
    position = numbers.index(week_number)
    return {**week, "previous_week": numbers[position - 1] if position else None, "next_week": numbers[position + 1] if position + 1 < len(numbers) else None,
            "weeks_total": len(numbers), "current_session": overview["current_session"]}


def _resources(activity: dict) -> list[dict]:
    found = [get_resource(store.db, resource_id) for resource_id in activity.get("resource_ids", [])]
    return [{**{key: item.get(key) for key in ("resource_id", "title", "provider", "resource_type", "url", "language", "level", "estimated_minutes", "learning_outcome", "cost_access", "last_checked_at")},
             "available": is_usable(item)} for item in found if item]


def lesson_detail(user_id: uuid.UUID, activity_id: str) -> dict:
    from backend import practice
    from backend.mistakes import lesson_mistakes

    roadmap = store.roadmaps.get(user_id) or {}
    planned = (roadmap.get("activity_plan") or {}).get(activity_id)
    activity = store.get_activity(activity_id)
    if not planned or planned.get("kind", "LEARNING") != "LEARNING" or not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bài học này không có trong lộ trình hiện tại của bạn.")
    states = lesson_states(user_id)
    state = states[activity_id]
    order = list(states)
    position = order.index(activity_id)
    weeks = [week["week_number"] for week in (roadmap.get("schedule") or {}).get("scheduled_weeks", []) if any(item.get("activity_id") == activity_id for item in week["activities"])]
    checks = lesson_checks(user_id, activity_id)
    reviews = _review_tests(user_id).get(activity_id, [])
    prerequisites = [{"activity_id": item, "title": (store.get_activity(item) or {}).get("title", item), "learning_state": (states.get(item) or {}).get("learning_state")} for item in activity.get("prerequisites", [])]
    return {
        "activity": {key: activity.get(key) for key in ("activity_id", "title", "target_skill", "target_level", "estimated_hours", "learning_objectives", "learning_outcome")},
        "skill_name": (store.get_skill(activity.get("target_skill")) or {}).get("skill_name"),
        "plan": planned, "weeks": weeks, "prerequisites": prerequisites, "carried_over": bool(planned.get("carried_over")),
        "previous_lesson": order[position - 1] if position else None, "next_lesson": order[position + 1] if position + 1 < len(order) else None,
        "state": state, "resources": _resources(activity), "practice": practice.exercises_for(user_id, activity_id),
        "sessions": session_history(user_id, activity_id), "current_session": session_view(current_session(user_id)),
        "checks": [check_summary(row) for row in checks if row["status"] in (*GRADED, "PENDING", "UNAVAILABLE")],
        "reviews": [review_summary(row) for row in reviews if row["status"] in (*GRADED, "PENDING")],
        "review_presets": list(REVIEW_PRESETS), "review_limits": {"min": MIN_CYCLE_DAYS, "max": MAX_CYCLE_DAYS},
        "mistakes": lesson_mistakes(user_id, activity),
    }


def roadmap_activity(user_id: uuid.UUID, activity_id: str) -> tuple[dict, dict]:
    roadmap = store.roadmaps.get(user_id) or {}
    planned = (roadmap.get("activity_plan") or {}).get(activity_id)
    activity = store.get_activity(activity_id)
    if not planned or planned.get("kind", "LEARNING") != "LEARNING" or not activity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bài học này không có trong lộ trình hiện tại của bạn.")
    return roadmap, activity

