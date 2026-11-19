"""Learner-facing review cycles, reminders and mini-tests (F10, F20, F21)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.ai_service.assessment_provider import is_enabled as ai_is_enabled
from backend.ai_service.gateway import is_available as gateway_available
from backend.auth import AuthenticatedUser, get_current_user
from backend.career_process import CAREERS
from backend.catalog import get_resource, is_usable, list_resources
from backend.clock import utcnow
from backend.database import dumps
from backend.engine.test_engine import estimate_level, public_item, score_item
from backend.learning_cycle_service import (
    ALLOWED_PRESET_CYCLES, MAX_CYCLE_DAYS, MIN_CYCLE_DAYS, PASS_THRESHOLD, REMINDER_KINDS, _checkin_view, _supersede, active_checkin, create_checkin,
    get_preferences, local_today, reminder_view, apply_kind_preferences, run_scan, save_preferences, validate_cycle, zone_of,
)
from backend.lesson_checks import LESSON_CHECK_KIND, QUIZ_LEVEL_CEILING
from backend.store import store

from backend.engine import container_sandbox  # noqa: E402

router = APIRouter(tags=["F20/F21 - Reminders & Mini-tests"])


def demo_tools_enabled() -> bool:
    return os.getenv("CAREERADAPT_ENABLE_DEMO_TOOLS", "false").lower() == "true" and os.getenv("CAREERADAPT_ENV", "development").lower() != "production"


class ScheduleRequest(BaseModel):
    action: Literal["SET_CYCLE", "SNOOZE", "CANCEL", "SIMULATE_DUE"] = "SET_CYCLE"
    cycle_days: Optional[int] = Field(default=None, description="3, 7, 14, 30 hoặc số ngày tùy chỉnh")
    anchor_date: Optional[date] = None
    snooze_days: int = Field(default=1, ge=1, le=30)


class SnoozeRequest(BaseModel):
    days: int = Field(default=1, ge=1, le=30)


class PreferenceRequest(BaseModel):
    timezone: Optional[str] = Field(default=None, max_length=60)
    default_cycle_days: Optional[int] = None
    enabled_kinds: Optional[dict[str, bool]] = None


class MicroSubmission(BaseModel):
    responses: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: Optional[str] = Field(default=None, max_length=100)


def clean_responses(items: list[dict], responses: dict[str, Any]) -> dict[str, Any]:
    """Known questions only, each answer a number, a short string or a short list of strings."""
    known = {item["item_id"] for item in items}
    clean: dict[str, Any] = {}
    for key, value in responses.items():
        if key not in known or value is None:
            continue
        if (isinstance(value, str) and len(value) <= 200) or (isinstance(value, (int, float)) and not isinstance(value, bool)):
            clean[key] = value
        elif isinstance(value, list) and len(value) <= 20 and all(isinstance(part, str) and len(part) <= 40 for part in value):
            clean[key] = value
        else:
            raise HTTPException(status_code=422, detail="Câu trả lời không hợp lệ.")
    return clean


def _require_checkin(user_id: uuid.UUID, activity_id: str) -> dict:
    checkin = active_checkin(user_id, activity_id)
    if not checkin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hoạt động này chưa có lịch kiểm tra lại.")
    return checkin


def schedule_review_after_pass(user_id: uuid.UUID, activity: dict, roadmap_version: Optional[int]) -> dict:
    """Review N days after the pass, N being the cycle chosen when the lesson was first started."""
    preferences = get_preferences(user_id)
    plan = store.db.one("SELECT review_cycle_days FROM lesson_plans WHERE user_id = ? AND activity_id = ? AND archived_by_run IS NULL", (str(user_id), activity["activity_id"]))
    days = int(plan["review_cycle_days"]) if plan else int(preferences["default_cycle_days"])
    checkin = create_checkin(user_id, activity, days, local_today(preferences), roadmap_version, preferences["timezone"])
    store.add_history_event(user_id, "REVIEW_SCHEDULED", f"Lịch ôn tập {activity.get('title', activity['activity_id'])}: sau {days} ngày", meta={"activity_id": activity["activity_id"], "checkin_id": checkin["checkin_id"]})
    return checkin


@router.patch("/activities/{id}/schedule")
def update_schedule(id: str, body: ScheduleRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Đặt chu kỳ, hoãn hoặc hủy lịch kiểm tra lại. Lịch cũ được giữ trong lịch sử."""
    user_id = current_user.user_id
    activity = store.get_activity(id)
    if not activity:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy học phần '{id}'.")
    preferences = get_preferences(user_id)
    roadmap_version = (store.roadmaps.get(user_id) or {}).get("roadmap_version")
    if body.action == "SET_CYCLE":
        if store.db.one("SELECT 1 FROM lesson_plans WHERE user_id = ? AND activity_id = ? AND archived_by_run IS NULL", (str(user_id), id)):
            raise HTTPException(status_code=409, detail="Thời gian kiểm tra lại của bài này đã được chốt khi bạn bắt đầu học nên không đổi được.")
        if body.cycle_days is None:
            raise HTTPException(status_code=422, detail="Hãy chọn chu kỳ kiểm tra lại.")
        anchor = body.anchor_date or local_today(preferences)
        try:
            checkin = create_checkin(user_id, activity, body.cycle_days, anchor, roadmap_version, preferences["timezone"])
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error))
        store.add_history_event(user_id, "CYCLE_SET", f"Đặt chu kỳ {body.cycle_days} ngày cho {activity['title']}", meta={"activity_id": id, "checkin_id": checkin["checkin_id"]})
        return checkin
    checkin = _require_checkin(user_id, id)
    now = utcnow()
    if body.action == "SNOOZE":
        due = max(now, datetime.fromisoformat(checkin["due_at"])) + timedelta(days=body.snooze_days)
        with store.db.transaction():
            store.db.execute("UPDATE learning_checkins SET status = 'SCHEDULED', due_at = ?, updated_at = ? WHERE checkin_id = ?", (due.isoformat(), now.isoformat(), checkin["checkin_id"]))
            store.db.execute("UPDATE reminder_jobs SET status = 'SUPERSEDED', updated_at = ? WHERE ref_id = ? AND status IN ('ACTIVE', 'SNOOZED')", (now.isoformat(), checkin["checkin_id"]))
            store.db.execute("UPDATE micro_assessments SET status = 'CANCELLED' WHERE checkin_id = ? AND status = 'PENDING'", (checkin["checkin_id"],))
        store.add_history_event(user_id, "CYCLE_POSTPONED", f"Hoãn kiểm tra lại {activity['title']} {body.snooze_days} ngày", meta={"activity_id": id})
    elif body.action == "CANCEL":
        with store.db.transaction():
            _supersede(checkin, None)
            store.db.execute("UPDATE learning_checkins SET status = 'CANCELLED' WHERE checkin_id = ?", (checkin["checkin_id"],))
        store.add_history_event(user_id, "CYCLE_CANCELLED", f"Hủy lịch kiểm tra lại {activity['title']}", meta={"activity_id": id})
    else:
        if not demo_tools_enabled():
            raise HTTPException(status_code=403, detail="Công cụ giả lập chỉ bật khi trình diễn.")
        store.db.execute("UPDATE learning_checkins SET due_at = ?, updated_at = ? WHERE checkin_id = ?", (now.isoformat(), now.isoformat(), checkin["checkin_id"]))
        run_scan(user_id)
    return _checkin_view(store.db.one("SELECT * FROM learning_checkins WHERE checkin_id = ?", (checkin["checkin_id"],)))


@router.get("/me/checkins")
def list_checkins(current_user: AuthenticatedUser = Depends(get_current_user)):
    rows = store.db.query("SELECT * FROM learning_checkins WHERE user_id = ? AND status != 'ARCHIVED' ORDER BY created_at DESC", (str(current_user.user_id),))
    return [_checkin_view(row) for row in rows]


@router.get("/me/reminders")
def list_reminders(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Nhắc đến hạn và mini-test cần làm."""
    run_scan(current_user.user_id)
    user = str(current_user.user_id)
    preferences = get_preferences(current_user.user_id)
    today = local_today(preferences)
    active = [reminder_view(row, today) for row in store.db.query("SELECT * FROM reminder_jobs WHERE user_id = ? AND status = 'ACTIVE' ORDER BY scheduled_at DESC", (user,))]
    snoozed = [reminder_view(row, today) for row in store.db.query("SELECT * FROM reminder_jobs WHERE user_id = ? AND status = 'SNOOZED' ORDER BY snooze_until", (user,))]
    micro = store.db.query("SELECT micro_id, checkin_id, skill_code, activity_id, status, created_at, due_at FROM micro_assessments WHERE user_id = ? AND status = 'PENDING' ORDER BY created_at", (user,))
    # Most pressing first: overdue, then review tests that are due, then what is coming up, then schedule notes.
    order = {"OVERDUE": 0, "MINI_TEST": 1, "DUE_SOON": 2, "UNSCHEDULED": 3}
    active.sort(key=lambda item: (order.get(item["state"], 9), item["days"] if item["days"] is not None else 0))
    return {
        "active": active, "snoozed": snoozed, "unread_count": len(active), "pending_mini_tests": micro,
        "counts": {kind: sum(1 for item in active if item["kind"] == kind) for kind in REMINDER_KINDS},
        "overdue_count": sum(1 for item in active if item["state"] == "OVERDUE"),
        "upcoming": [_checkin_view(row) for row in store.db.query("SELECT * FROM learning_checkins WHERE user_id = ? AND status = 'SCHEDULED' ORDER BY due_at", (user,))],
        "preferences": preferences,
    }


def _owned_reminder(reminder_id: str, user: AuthenticatedUser, open_only: bool = True) -> dict:
    row = store.db.one("SELECT * FROM reminder_jobs WHERE reminder_id = ? AND user_id = ?", (reminder_id, str(user.user_id)))
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhắc nhở.")
    # A reminder that was already seen, finished or replaced stays closed: acting on it must not bring it back.
    if open_only and row["status"] not in ("ACTIVE", "SNOOZED"):
        raise HTTPException(status_code=409, detail="Nhắc nhở này đã được xử lý.")
    return row


@router.post("/me/reminders/dismiss-all")
def dismiss_all_reminders(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Đánh dấu đã xem mọi nhắc đang hiện, trừ mini-test đến hạn (phải làm, hoãn hoặc đổi lịch)."""
    done = store.db.execute("UPDATE reminder_jobs SET status = 'DISMISSED', updated_at = ? WHERE user_id = ? AND status = 'ACTIVE' AND kind != 'MINI_TEST'",
                            (utcnow().isoformat(), str(current_user.user_id))).rowcount
    return {"dismissed": done}


@router.post("/me/reminders/{reminder_id}/resume")
def resume_reminder(reminder_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Nhắc lại ngay: đưa một nhắc đang tạm hoãn trở lại danh sách cần xử lý."""
    row = _owned_reminder(reminder_id, current_user)
    if row["status"] != "SNOOZED":
        raise HTTPException(status_code=409, detail="Nhắc nhở này không ở trạng thái tạm hoãn.")
    store.db.execute("UPDATE reminder_jobs SET status = 'ACTIVE', snooze_until = NULL, updated_at = ? WHERE reminder_id = ?", (utcnow().isoformat(), reminder_id))
    return {"reminder_id": reminder_id, "status": "ACTIVE"}


@router.post("/me/reminders/{reminder_id}/snooze")
def snooze_reminder(reminder_id: str, body: SnoozeRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Nhắc lại sau: nhắc tạm ẩn và quay lại đúng hàng cũ, không tạo bản sao."""
    row = _owned_reminder(reminder_id, current_user)
    until = (utcnow() + timedelta(days=body.days)).isoformat()
    store.db.execute("UPDATE reminder_jobs SET status = 'SNOOZED', snooze_until = ?, updated_at = ? WHERE reminder_id = ?", (until, utcnow().isoformat(), reminder_id))
    if row["kind"] == "MINI_TEST" and row["ref_id"]:
        store.db.execute("UPDATE learning_checkins SET status = 'SNOOZED', updated_at = ? WHERE checkin_id = ?", (utcnow().isoformat(), row["ref_id"]))
    store.add_history_event(current_user.user_id, "REMINDER_SNOOZED", f"{row['title']} (nhắc lại sau {body.days} ngày)")
    return {"reminder_id": reminder_id, "status": "SNOOZED", "snooze_until": until}


@router.post("/me/reminders/{reminder_id}/dismiss")
def dismiss_reminder(reminder_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    row = _owned_reminder(reminder_id, current_user)
    if row["kind"] == "MINI_TEST":
        raise HTTPException(status_code=409, detail="Mini-test đến hạn không thể bỏ qua ở đây. Hãy làm ngay, nhắc lại sau hoặc điều chỉnh lịch.")
    store.db.execute("UPDATE reminder_jobs SET status = 'DISMISSED', updated_at = ? WHERE reminder_id = ?", (utcnow().isoformat(), reminder_id))
    return {"reminder_id": reminder_id, "status": "DISMISSED"}


@router.get("/me/reminder-preferences")
def read_preferences(current_user: AuthenticatedUser = Depends(get_current_user)):
    return {**get_preferences(current_user.user_id), "preset_cycles": list(ALLOWED_PRESET_CYCLES), "min_cycle_days": MIN_CYCLE_DAYS, "max_cycle_days": MAX_CYCLE_DAYS, "kinds": list(REMINDER_KINDS)}


@router.put("/me/reminder-preferences")
def update_preferences(body: PreferenceRequest, current_user: AuthenticatedUser = Depends(get_current_user)):
    preferences = get_preferences(current_user.user_id)
    try:
        if body.timezone:
            zone_of(body.timezone)
            preferences["timezone"] = body.timezone
        if body.default_cycle_days is not None:
            validate_cycle(body.default_cycle_days)
            preferences["default_cycle_days"] = body.default_cycle_days
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    if body.enabled_kinds is not None:
        preferences["enabled_kinds"] = {kind: bool(body.enabled_kinds.get(kind, preferences["enabled_kinds"].get(kind, True))) for kind in REMINDER_KINDS}
    saved = save_preferences(current_user.user_id, preferences)
    apply_kind_preferences(current_user.user_id, preferences)
    return saved


def _micro(micro_id: str, user: AuthenticatedUser) -> dict:
    row = store.db.one("SELECT * FROM micro_assessments WHERE micro_id = ? AND user_id = ?", (micro_id, str(user.user_id)))
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy mini-test.")
    return {**row, "payload": json.loads(row["payload"])}


def _micro_view(row: dict) -> dict:
    payload = row["payload"]
    data = {key: row[key] for key in ("micro_id", "skill_code", "activity_id", "status", "due_at", "created_at", "submitted_at", "attempts", "bank_version")}
    data.update({"activity_title": payload.get("activity_title"), "time_limit_minutes": payload.get("time_limit_minutes"), "pass_threshold": payload.get("pass_threshold"),
                 "kind": payload.get("kind", "MINI_TEST"), "learning_objectives": payload.get("learning_objectives", []), "attempt_no": payload.get("attempt_no")})
    if row["status"] == "PENDING":
        data["items"] = [public_item(item, payload["option_orders"].get(item["item_id"])) for item in payload["items"]]
        data["draft"] = payload.get("draft", {})
    elif payload.get("result"):
        data["result"] = payload["result"]
    return data


@router.get("/micro-tests")
def list_micro_tests(current_user: AuthenticatedUser = Depends(get_current_user)):
    run_scan(current_user.user_id)
    rows = store.db.query("SELECT * FROM micro_assessments WHERE user_id = ? AND status != 'ARCHIVED' ORDER BY created_at DESC", (str(current_user.user_id),))
    return [_micro_view({**row, "payload": json.loads(row["payload"])}) for row in rows]


@router.get("/micro-tests/{micro_id}")
def get_micro_test(micro_id: str, current_user: AuthenticatedUser = Depends(get_current_user)):
    row = _micro(micro_id, current_user)
    # The assistant stays closed from here until the mini-test is submitted.
    store.db.execute("UPDATE micro_assessments SET payload = json_set(payload, '$.opened_at', ?) WHERE micro_id = ? AND status = 'PENDING'", (utcnow().isoformat(), micro_id))
    return _micro_view(row)


def _review_resources(activity: dict, skill_code: str) -> list[dict]:
    attached = [get_resource(store.db, resource_id) for resource_id in activity.get("resource_ids", [])]
    usable = [item for item in attached if item and is_usable(item)]
    if not usable:
        usable = [item for item in list_resources(store.db) if skill_code in item.get("skill_ids", [])][:3]
    return [{key: item.get(key) for key in ("resource_id", "title", "provider", "url", "estimated_minutes", "learning_outcome")} for item in usable]


def grade_micro(items: list[dict], responses: dict[str, Any], threshold: float = PASS_THRESHOLD) -> dict:
    """Same rules as every assessment: a blank item scores zero and an all-blank test is not graded."""
    answered = [item for item in items if responses.get(item["item_id"]) not in (None, "", [])]
    if not answered:
        return {"status": "INCOMPLETE", "score": None, "passed": None, "answered": 0, "total": len(items), "item_results": [], "weak_topics": [], "levels": {}}
    earned = possible = 0.0
    results, levels, weak = [], {}, {}
    for item in items:
        credit = score_item(item, responses.get(item["item_id"]))
        points = float(store.difficulty_points.get(str(item["level"]), item["level"]))
        earned += credit * points
        possible += points
        stored = levels.get(item["level"], (0.0, 0))
        levels[item["level"]] = (stored[0] + credit, stored[1] + 1)
        if credit < 1:
            weak[item.get("topic") or item["skill_code"]] = True
        results.append({
            "item_id": item["item_id"], "stem": item.get("stem"), "topic": item.get("topic"), "level": item["level"], "credit": credit, "answered": item in answered,
            "points_earned": round(credit * points, 2), "points_possible": points, "explanation": item.get("explanation", ""),
        })
    score = round(100 * earned / possible, 2) if possible else 0.0
    correct = sum(1 for result in results if result["credit"] >= 1)
    strong = [topic for topic in dict.fromkeys(result["topic"] for result in results if result["credit"] >= 1) if topic and topic not in weak]
    return {"status": "GRADED", "score": score, "passed": score >= threshold, "answered": len(answered), "total": len(items), "item_results": results,
            "weak_topics": list(weak), "strong_topics": strong, "levels": levels,
            "counts": {"correct": correct, "wrong": len(answered) - correct, "unanswered": len(items) - len(answered)}}


@router.post("/micro-tests/{micro_id}/submissions")
def submit_micro_test(micro_id: str, body: MicroSubmission, current_user: AuthenticatedUser = Depends(get_current_user)):
    """Nộp mini-test; chỉ kết quả hợp lệ và đạt mới được ghi nhận vào hồ sơ kỹ năng."""
    user_id = current_user.user_id
    row = _micro(micro_id, current_user)
    payload = row["payload"]
    if row["status"] in {"PASSED", "FAILED"}:
        if body.idempotency_key and row["idempotency_key"] == body.idempotency_key:
            return {**payload["result"], "is_duplicate": True}
        raise HTTPException(status_code=409, detail="Mini-test này đã được nộp.")
    if row["status"] not in {"PENDING", "INCOMPLETE"}:
        raise HTTPException(status_code=409, detail="Mini-test này không còn hiệu lực.")
    items = payload["items"]
    lesson = payload.get("kind") == LESSON_CHECK_KIND
    threshold = float(payload.get("pass_threshold") or PASS_THRESHOLD)
    graded = grade_micro(items, clean_responses(items, body.responses), threshold)
    now = utcnow().isoformat()
    activity = store.get_activity(row["activity_id"]) or {}
    skill = row["skill_code"]
    if graded["status"] == "INCOMPLETE":
        payload["result"] = {"status": "INCOMPLETE", "score": None, "passed": None, "message": "Bạn chưa trả lời câu nào nên bài chưa được chấm. Hồ sơ kỹ năng không thay đổi; hãy làm lại khi sẵn sàng.", "is_duplicate": False}
        store.db.execute("UPDATE micro_assessments SET attempts = attempts + 1, payload = ? WHERE micro_id = ?", (dumps(payload), micro_id))
        return payload["result"]

    levels = graded.pop("levels")
    profile = store.get_or_create_profile(user_id)
    previous = (profile.get("assessed_skills", {}).get(skill) or {}).get("level")
    estimated, _ = estimate_level(levels)
    target = int(activity.get("target_level", estimated) or 1)
    level_short = False
    if lesson and graded["passed"] and target in levels and estimated < target:
        # The completion check has questions at every level up to the lesson's level, so it must prove that level.
        graded["passed"] = False
        level_short = True
    new_level = previous
    # A form issued before every level was covered may skip level 1: it cannot set a first level.
    if graded["passed"] and (previous is not None or 1 in levels):
        observed = min(estimated, target)
        if lesson:
            # A lesson check covers every level up to the lesson's level: it can confirm all of them at once,
            # up to the quiz ceiling. Level 3 is confirmed by practical work (entry exam, final assessment).
            ceiling = min(observed, QUIZ_LEVEL_CEILING)
        else:
            # A short review can confirm one step of progress at a time.
            ceiling = observed if previous is None else min(observed, previous + 1)
        # Never lowers a level.
        new_level = ceiling if previous is None else max(previous, ceiling)
    result = {
        **graded, "status": "PASSED" if graded["passed"] else "FAILED", "micro_id": micro_id, "skill_code": skill, "activity_id": row["activity_id"], "previous_level": previous,
        "current_level": new_level, "pass_threshold": threshold, "bank_version": row["bank_version"], "roadmap_version": payload.get("roadmap_version"),
        "kind": payload.get("kind", "MINI_TEST"), "activity_title": payload.get("activity_title"),
        "scope_note": "Kết quả chỉ phản ánh nội dung của bài kiểm tra ngắn này, không phải chứng chỉ nghề hay bảo đảm được nhận thực tập.",
        "is_duplicate": False,
    }
    if not graded["passed"]:
        result["review_resources"] = _review_resources(activity, skill)
        if lesson:
            result["can_retry"] = True
            result["message"] = "Chưa đạt. Học phần chuyển sang Cần ôn tập; hãy ôn phần còn yếu rồi làm lại. Kết quả này không hạ mức năng lực đã có."
            if level_short:
                result["level_short"] = True
                result["required_level"] = target
                result["message"] = (f"Điểm đạt ngưỡng nhưng các câu mức {target} chưa đủ đúng, nên chưa xác nhận được mức {target} của học phần. "
                                     "Hãy ôn phần còn yếu rồi làm lại. Kết quả này không hạ mức năng lực đã có.")
        else:
            result["suggested_cycle_days"] = 3
            result["message"] = "Chưa đạt. Hãy ôn lại phần yếu và đặt lịch kiểm tra tiếp; kết quả này không hạ mức năng lực đã có."
    elif lesson:
        result["message"] = ("Đạt. Học phần đã được xác minh và kết quả được lưu làm bằng chứng kỹ năng." if new_level != previous
                             else "Đạt. Học phần đã được xác minh; mức năng lực giữ nguyên vì bài này không đo vượt mức hiện tại.")
    else:
        result["message"] = "Đạt. Kết quả được lưu làm bằng chứng tiến bộ." if new_level != previous else "Đạt. Kết quả được lưu; mức năng lực giữ nguyên vì bài ngắn không đo vượt mức hiện tại."
    payload["result"] = result
    with store.db.transaction():
        store.db.execute(
            "UPDATE micro_assessments SET status = ?, attempts = attempts + 1, idempotency_key = ?, submitted_at = ?, payload = ? WHERE micro_id = ?",
            (result["status"], body.idempotency_key, now, dumps(payload), micro_id),
        )
        store.db.execute("UPDATE learning_checkins SET status = 'COMPLETED', updated_at = ? WHERE checkin_id = ?", (now, row["checkin_id"]))
        store.db.execute("UPDATE reminder_jobs SET status = 'DONE', updated_at = ? WHERE ref_id = ? AND status IN ('ACTIVE', 'SNOOZED')", (now, row["checkin_id"]))
        if graded["passed"] and new_level is not None:
            store.add_skill_evidence(user_id, skill, int(new_level), "MINI_TEST", micro_id, score=graded["score"] / 100,
                                     task_id=f"{'LESSON' if lesson else 'MINI'}:{row['activity_id']}", scope_note=result["scope_note"], created_at=now)
            if new_level != previous:
                profile.setdefault("assessed_skills", {})[skill] = {
                    "level": int(new_level), "score": graded["score"] / 100, "confidence": None, "submission_id": micro_id, "assessed_at": now,
                    "assessment_status": "VERIFIED", "source_type": "MINI_TEST", "task_id": f"{'LESSON' if lesson else 'MINI'}:{row['activity_id']}", "scope_note": result["scope_note"],
                }
                profile["updated_at"] = now
                store.persist_user_runtime(user_id)
    if lesson and graded["passed"]:
        review = schedule_review_after_pass(user_id, activity, payload.get("roadmap_version"))
        result["review_due_at"] = review["due_at"]
        result["review_cycle_days"] = review["cycle_days"]
        payload["result"] = result
        store.db.execute("UPDATE micro_assessments SET payload = ? WHERE micro_id = ?", (dumps(payload), micro_id))
    if graded["passed"] and new_level is not None and new_level != previous:
        from backend.api.roadmaps import replan

        result["roadmap_update"] = replan(user_id, f"Mức {skill} được xác thực từ {previous if previous is not None else 'chưa đánh giá'} lên {new_level}.")
        if result["roadmap_update"]["changed"]:
            payload["result"] = result
            store.db.execute("UPDATE micro_assessments SET payload = ? WHERE micro_id = ?", (dumps(payload), micro_id))
    label = "Kiểm tra học phần" if lesson else "Mini-test"
    store.add_history_event(user_id, "LESSON_CHECK_SUBMITTED" if lesson else "MINI_TEST_SUBMITTED", f"{label} {activity.get('title', row['activity_id'])}: {graded['score']:g}/100 ({result['status']})",
                            version=str(row["bank_version"]), meta={"micro_id": micro_id, "activity_id": row["activity_id"], "skill_code": skill, "roadmap_version": payload.get("roadmap_version")})
    return result


@router.get("/system/capabilities")
def capabilities(current_user: AuthenticatedUser = Depends(get_current_user)):
    """Cho giao diện biết tính năng nào thật sự đang bật, để không hiện nút vô tác dụng."""
    return {"ai_feedback_enabled": ai_is_enabled(), "assistant_ai_enabled": gateway_available(), "careers": list(CAREERS), "demo_tools_enabled": demo_tools_enabled(), "fault_injection_enabled": os.getenv("CAREERADAPT_ENABLE_FAULT_INJECTION", "false").lower() == "true" and os.getenv("CAREERADAPT_ENV", "development").lower() != "production",
            # Where learners' code runs: "process" (local subprocess) or "container" (Docker, no network).
            "code_sandbox": "container" if container_sandbox.use_container() else "process"}
